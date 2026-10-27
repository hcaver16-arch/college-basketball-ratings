#!/usr/bin/env python3
"""Courtside V115: research-only schema diagnosis and evidence-preserving normalization.

No network reads. Never invents completion/availability timestamps or venue verification.
The normalized table is NOT accepted as input to the strict V114 replay unless all
required source-supplied evidence is explicitly present.
"""
import argparse
import csv
import gzip
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

FIELDS = {
    'division': ('division', 'league'),
    'game_id': ('game_id', 'espn_game_id', 'event_id', 'competition_id', 'id'),
    'game_start_utc': ('game_start_utc', 'start_utc', 'start_time_utc', 'scheduled_start_utc', 'date_utc', 'start_date_utc', 'start_date'),
    'game_date_only': ('date', 'game_date', 'date_et', 'game_date_et', 'game_day'),
    'final_available_utc': ('final_available_utc', 'result_available_utc', 'result_observed_utc', 'completed_at_utc', 'final_timestamp_utc'),
    'home_id': ('home_id', 'home_team_id', 'home_team_espn_id', 'home_espn_id', 'homeid'),
    'away_id': ('away_id', 'away_team_id', 'away_team_espn_id', 'away_espn_id', 'awayid'),
    'home_points': ('home_points', 'home_score', 'home_pts', 'home_score_final'),
    'away_points': ('away_points', 'away_score', 'away_pts', 'away_score_final'),
    'neutral_site': ('neutral_site', 'neutral', 'is_neutral', 'neutral_flag'),
    'neutral_verified': ('neutral_verified', 'venue_verified', 'verified_venue'),
    'venue_source_url': ('venue_source_url', 'venue_evidence_url', 'neutral_source_url'),
    'result_source_url': ('result_source_url', 'final_source_url', 'boxscore_url'),
}

def canon(s): return re.sub(r'[^a-z0-9]', '', (s or '').casefold())

def path_label(p, root):
    try: return str(p.relative_to(root))
    except ValueError: return str(p)

def div_from_path(path):
    low = str(path).lower()
    if 'women' in low: return 'womens-college-basketball'
    if 'men' in low: return 'mens-college-basketball'
    return ''

def aware(s):
    if not s or not re.search(r'(?:Z|[+-]\d{2}:?\d{2})$', s.strip(), re.I): return None
    try:
        dt=datetime.fromisoformat(s.strip().replace('Z','+00:00'))
        return dt.astimezone(timezone.utc).isoformat() if dt.tzinfo else None
    except ValueError: return None

def score(s):
    try:
        v=float(s)
        return str(int(v)) if v.is_integer() and 0 <= v <= 250 else ''
    except (ValueError, TypeError): return ''

def boolean(s):
    v=str(s).strip().lower()
    if v in ('true','yes','1','y'): return 'true'
    if v in ('false','no','0','n'): return 'false'
    return ''

def discover(root):
    paths=[]
    for sub in ('data/historical_efficiency', 'data/historical_games', 'data/historical', 'data/history'):
        base=root/sub
        if base.exists(): paths.extend(p for p in base.rglob('*') if p.is_file() and (p.name.endswith('.csv') or p.name.endswith('.csv.gz')))
    # Explicitly include relevant history tables from prior V114, but label unsuitable ones.
    for sub in ('data/ratings','data/predictions'):
        base=root/sub
        if base.exists(): paths.extend(p for p in base.rglob('*') if p.is_file() and (p.name.endswith('.csv') or p.name.endswith('.csv.gz')) and ('history' in p.name.lower() or 'game_classification' in p.name.lower()))
    return sorted(set(paths))[:250]

def run(root, sources, out, max_rows):
    out.mkdir(parents=True, exist_ok=True)
    normalized_path=out/'candidate_games.csv'
    fieldnames=['division','game_id','game_start_utc','game_date_only','final_available_utc','home_id','away_id','home_points','away_points','neutral_site','neutral_verified','venue_source_url','result_source_url','source_file','source_row','source_field_mapping','missing_fields','evidence_status']
    inventories=[]; total=Counter(); missing_examples={}; seen_keys={}
    with normalized_path.open('w',newline='',encoding='utf-8') as outf:
        writer=csv.DictWriter(outf,fieldnames=fieldnames); writer.writeheader()
        for path in sources:
            label=path_label(path,root)
            item={'path':label,'exists':path.exists(),'rows_seen':0,'schema':[],'field_mapping':{},'field_population':{},'row_issue_counts':{},'candidate_rows_written':0,'strict_v114_ready_rows':0,'example_values':{}}
            if not path.exists():
                item['error']='file_not_found'; inventories.append(item);continue
            try:
                opening=gzip.open if str(path).endswith('.gz') else open
                with opening(path,'rt',newline='',encoding='utf-8-sig') as f:
                    reader=csv.DictReader(f)
                    headers=reader.fieldnames or []
                    item['schema']=headers
                    header_map={canon(h):h for h in headers if h}
                    mapping={key:next((header_map[canon(alias)] for alias in aliases if canon(alias) in header_map),None) for key, aliases in FIELDS.items()}
                    item['field_mapping']=mapping
                    pop=Counter(); issues=Counter(); example={}; strict=0; written=0
                    for line,raw in enumerate(reader,start=2):
                        if item['rows_seen']>=max_rows:
                            item['truncated_at_max_rows']=True; break
                        item['rows_seen']+=1;total['rows_scanned']+=1
                        r={key:str(raw.get(header,'') or '').strip() if header else '' for key,header in mapping.items()}
                        if not r['division']:r['division']=div_from_path(path)
                        for k,v in r.items():
                            if v: pop[k]+=1
                            if v and k not in example:example[k]=v[:75]
                        for k in ('game_start_utc','final_available_utc'):
                            if r[k] and not aware(r[k]):issues[k+'_not_timezone_aware']+=1
                            r[k]=aware(r[k]) or ''
                        for k in ('home_points','away_points'):r[k]=score(r[k])
                        for k in ('neutral_site','neutral_verified'):r[k]=boolean(r[k])
                        required=('game_id','game_start_utc','final_available_utc','home_id','away_id','home_points','away_points','neutral_site','neutral_verified')
                        missing=[k for k in required if not r[k]]
                        if r['home_id'] and r['away_id'] and r['home_id']==r['away_id']:
                            missing.append('different_home_away_ids')
                        if r['neutral_verified']!='true':
                            missing.append('independently_verified_venue')
                        if r['game_start_utc'] and r['final_available_utc'] and r['final_available_utc'] < r['game_start_utc']:
                            missing.append('chronological_final_availability')
                        if r['game_id'] and r['home_id'] and r['away_id']:
                            key=(r['division'],r['game_id'])
                            if key in seen_keys:
                                issues['repeated_division_game_id_across_sources']+=1
                            else:seen_keys[key]=label
                        for issue in set(missing):issues['missing_or_unverified_'+issue]+=1
                        # Don't emit rating history rows as games: require matching home/away IDs and scores.
                        structurally_game=bool(r['home_id'] and r['away_id'] and r['home_points'] and r['away_points'] and r['home_id'] != r['away_id'])
                        if not structurally_game:
                            issues['row_not_game_shaped']+=1
                            continue
                        status='strict_field_complete_not_proven' if not missing else 'incomplete_unverified_candidate'
                        if not missing:strict+=1
                        record={**r,'source_file':label,'source_row':line,'source_field_mapping':json.dumps({k:v for k,v in mapping.items() if v},sort_keys=True),'missing_fields':';'.join(sorted(set(missing))),'evidence_status':status}
                        writer.writerow({k:record.get(k,'') for k in fieldnames});written+=1;total['candidate_rows_written']+=1
                    item['field_population']=dict(pop);item['row_issue_counts']=dict(issues)
                    item['example_values']=example;item['candidate_rows_written']=written;item['strict_v114_ready_rows']=strict
                    total['strict_field_complete_rows_not_source_verified']+=strict
            except (OSError,UnicodeError,csv.Error,ValueError) as exc:item['error']=str(exc)[:300]
            inventories.append(item)
    summary={'version':115,'status':'RESEARCH_ONLY_SOURCE_SCHEMA_RECONSTRUCTION','production_modified':False,'game_archive_replay_authorized':False,'files_inspected':len(inventories),'totals':dict(total),'per_file':[{'path':i['path'],'rows_seen':i['rows_seen'],'candidate_rows_written':i['candidate_rows_written'],'strict_field_complete_rows':i['strict_v114_ready_rows'],'issue_counts':i['row_issue_counts'],'error':i.get('error')} for i in inventories],'outputs':['summary.json','report.md','inventory.json','candidate_games.csv'],'limitations':['Candidate table is NOT a validated historical event archive and must not be fed to live ratings or V114 without source review.','A time-looking field does not prove source observed availability; no timestamps or venue verification are synthesized.','Schema alias matching is conservative and may miss nested or nonstandard home/away fields.','Final-availability time is not inferred from score, date, game start, or file modification time.','No network fetch or source validation is performed; supplied verification flags are self-reported.','Rows lacking explicit both sides and scores are not emitted as game candidates.','Non-D1 opponents are not silently filtered.']}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (out/'inventory.json').write_text(json.dumps(inventories,indent=2)+'\n')
    md=['# Courtside V115 — Historical game schema and reconstruction report','','**Research only. Production untouched.**','',f"Files inspected: **{len(inventories)}**",f"CSV rows read: **{total['rows_scanned']}**",f"Structurally game-shaped rows: **{total['candidate_rows_written']}**",f"Rows containing every strict field (source evidence not independently proven): **{total['strict_field_complete_rows_not_source_verified']}**",'','## Per-file coverage','','| File | Rows | Game-shaped candidates | Strict-field-complete |','|---|---:|---:|---:|']
    for i in inventories:md.append(f"| `{i['path']}` | {i['rows_seen']} | {i['candidate_rows_written']} | {i['strict_v114_ready_rows']} |")
    md.extend(['','## Interpretation','','`inventory.json` contains the exact source headers, detected aliases, populated-field counts, and per-field rejection counts. `candidate_games.csv` retains source paths, source row numbers, and missing-evidence flags.','','Do not use incomplete candidates for historical predictive scoring. Missing result-availability timestamps and independent venue verification require source-backed collection, never estimation.','','## Next step','','Inspect the four historical-efficiency paired-game files in `inventory.json` first. For each missing field, obtain provider documentation or event-level records before attempting V114 again.'])
    (out/'report.md').write_text('\n'.join(md)+'\n')
    print(json.dumps({'status':summary['status'],'rows_scanned':total['rows_scanned'],'game_candidates':total['candidate_rows_written'],'output':str(out)}))

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--source',action='append',default=[]);p.add_argument('--out',default='data/historical_reconstruction_v115');p.add_argument('--max-rows',type=int,default=250000);args=p.parse_args()
    root=Path(args.root).resolve();paths=[Path(s) if Path(s).is_absolute() else root/s for s in args.source] if args.source else discover(root)
    out=Path(args.out);out=out if out.is_absolute() else root/out
    run(root,paths,out,max(1,args.max_rows))
if __name__=='__main__':main()

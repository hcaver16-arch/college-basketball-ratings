#!/usr/bin/env python3
"""V112 research-only calibration readiness: never alters prediction or ratings inputs."""
import argparse, csv, gzip, hashlib, json, math, re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DIVS=('mens-college-basketball','womens-college-basketball')
PARAMS={'home_advantage_points':[2,2.5,3,3.5,4], 'ridge':[4,6,8,10,12], 'margin_cap':[25,30,40,50], 'blend_full_weight_games':[15,20,25,30,35], 'roster_scenario':['as_saved_no_extra','v105_extra_only_if_not_already_counted'], 'missing_prior':['missing_as_missing','zero_prior','conference_peer_research_only']}
TARGETS={'v97_forecasts':'data/prospective/2026-27/forecasts.csv','v97_results':'data/prospective/2026-27/results.csv','v109_pairs':'data/prospective/2026-27/roster_pairs_v109.csv','v105_summary':'data/roster_sensitivity_v105/summary.json','v111_summary':'data/rating_audit_v111/summary.json'}
TIME_KEYS=('paired_created_utc','baseline_forecast_created_utc','forecast_created_utc','created_utc','forecast_created_at','forecast_timestamp','prediction_created_utc','as_of_utc','timestamp_utc')
GAME_KEYS=('game_id','Game ID','event_id','id')

def load_csv(path):
    op=gzip.open if path.suffix=='.gz' else open
    with op(path,'rt',newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        fields=reader.fieldnames or []
        rows=list(reader)
    return fields,rows

def timeparse(v):
    if not v:return None
    try:
        d=datetime.fromisoformat(str(v).strip().replace('Z','+00:00'))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except (ValueError,TypeError): return None

def first(fields, names):return next((x for x in names if x in fields),None)

def csv_summary(path,kind):
    result={'exists':path.is_file(),'path':str(path),'kind':kind}
    if not result['exists']:return result
    try: fields,rows=load_csv(path)
    except (OSError,UnicodeError,csv.Error) as e: result['read_error']=str(e);return result
    result.update(rows=len(rows),columns=fields)
    timekey=first(fields,TIME_KEYS)
    startkey=first(fields,('game_start_utc','start_utc','tipoff_utc','game_date_utc'))
    gamekey=first(fields,GAME_KEYS)
    result['time_column']=timekey;result['start_column']=startkey;result['game_id_column']=gamekey
    if timekey:
        parseable=sum(timeparse(r.get(timekey)) is not None for r in rows)
        result['timestamp_parseable']=parseable
        result['timestamp_missing_or_invalid']=len(rows)-parseable
    if timekey and startkey:
        valid=0;late=0;unverifiable=0
        for r in rows:
            a,b=timeparse(r.get(timekey)),timeparse(r.get(startkey))
            if not a or not b:unverifiable+=1
            elif a<b:valid+=1
            else:late+=1
        result['pregame_timing']={'before_tipoff':valid,'at_or_after_tipoff':late,'unverifiable':unverifiable}
    if gamekey:
        ids=[r.get(gamekey,'').strip() for r in rows if r.get(gamekey,'').strip()]
        result['distinct_game_ids']=len(set(ids));result['repeated_game_id_rows']=len(ids)-len(set(ids))
    return result

def safe_json(path):
    if not path.exists(): return None
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return None

def structural_audit(root):
    source=root/'rating_engine.py'
    if not source.is_file():return {'exists':False}
    raw=source.read_text(encoding='utf-8')
    return {'exists':True,'sha256':hashlib.sha256(raw.encode()).hexdigest(), 'v111_expected_sha256':'3e058fea5aaacc0f0a8870ead49fe9a54bfe37054b561e42f2d9ef2bad236adb', 'source_changed_since_v111':hashlib.sha256(raw.encode()).hexdigest()!='3e058fea5aaacc0f0a8870ead49fe9a54bfe37054b561e42f2d9ef2bad236adb', 'mentions_prior_roster_adjustment':('Preseason roster adjustment' in raw), 'id_cast_occurrences':len(re.findall(r'\bstr\(',raw))}

def rating_snapshot(root,div):
    path=next((p for p in (root/'data/ratings'/div/'latest.csv.gz',root/'data/ratings'/div/'latest.csv') if p.exists()),None)
    if not path:return {'exists':False}
    s=csv_summary(path,'latest_ratings')
    if 'read_error' in s:return s
    fields,rows=load_csv(path)
    prior_key=first(fields,('Preseason roster adjustment','roster_adjustment'))
    prior_values=[];nonzero=0;invalid=0
    if prior_key:
        for r in rows:
            try:
                v=float(r.get(prior_key) or 0)
                if not math.isfinite(v):raise ValueError()
                prior_values.append(v)
                nonzero+=abs(v)>1e-10
            except (ValueError,TypeError):invalid+=1
    s['preseason_roster_adjustment']={'column':prior_key,'nonzero_rows':nonzero,'invalid_rows':invalid,'mean_absolute':round(sum(map(abs,prior_values))/len(prior_values),5) if prior_values else None}
    s['double_counting_risk']='PRESENT: ratings include nonzero saved roster adjustment; do not add V105 blindly' if nonzero else 'NO NONZERO SAVED ADJUSTMENTS DETECTED; overlap not otherwise ruled out' if prior_key else 'UNKNOWN: saved column absent'
    id_key=first(fields,('Team ID','team_id'))
    if id_key:s['team_id_sample']=[r.get(id_key,'') for r in rows[:3]]
    s['latest_is_valid_historical_training_archive']=False
    return s

def discover(root):
    # Manifest only: do not deserialize historical data or claim as-of safety.
    roots=[root/'data'/'historical',root/'data'/'backtests',root/'data'/'research',root/'data'/'prospective',root/'data'/'rosters']
    entries=[]
    for base in roots:
        if not base.exists():continue
        for p in sorted(base.rglob('*')):
            if not p.is_file() or p.suffix.lower() not in ('.csv','.gz','.json','.parquet'):continue
            if len(entries)>=250:break
            try:size=p.stat().st_size
            except OSError:continue
            entries.append({'path':str(p.relative_to(root)),'size_bytes':size,'looks_like_pregame_snapshot':bool(re.search(r'(forecast|predic|as.of|snapshot)',str(p),re.I)),'historical_availability_verified':False})
    return {'sample_files':entries,'file_count_listed':len(entries),'truncated':len(entries)>=250,'note':'Path/filename inspection only. Historical availability and lack of leakage are not established.'}

def judge(a):
    fc=a['prospective_inputs']['v97_forecasts'];result=a['prospective_inputs']['v97_results'];pairs=a['prospective_inputs']['v109_pairs']
    paired_games=pairs.get('rows',0) if pairs.get('exists') else 0
    completed_results=result.get('rows',0) if result.get('exists') else 0
    valid_timing=(pairs.get('pregame_timing') or {}).get('before_tipoff',0)
    pairing_ready=paired_games>0 and valid_timing==paired_games and completed_results>0
    saved_overlaps=any(a['ratings'][div]['preseason_roster_adjustment']['nonzero_rows']>0 for div in DIVS if a['ratings'][div].get('exists') and a['ratings'][div].get('preseason_roster_adjustment'))
    return {'can_run_historical_hyperparameter_search':False,'why_historical_blocked':'No independently validated historical walk-forward dataset, per-game as-of ratings and matching period-correct roster snapshots have been demonstrated by this readiness audit.', 'can_run_paired_prospective_scoring':pairing_ready, 'why_prospective_blocked':None if pairing_ready else 'Await locked forecasts created before tipoff and corresponding completed results; V112 does not manufacture a backtest.', 'roster_addition_risk': 'Potential double-counting: saved preseason adjustments exist' if saved_overlaps else 'Cannot rule out feature overlap from current files', 'eligible_parameter_grid':PARAMS, 'hyperparameter_selection_performed':False, 'backtest_metrics_computed':False}

def markdown(a):
    j=a['decision'];lines=['# Courtside V112 — Historical calibration readiness','', '**RESEARCH ONLY. No rating, prediction, website, or V97/V109 files altered.**','', '## Calibration decision','',f"- Historical tuning permitted: **{'YES' if j['can_run_historical_hyperparameter_search'] else 'NO'}**",f"- Why: {j['why_historical_blocked']}",f"- Prospective paired scoring readiness: **{'YES' if j['can_run_paired_prospective_scoring'] else 'NOT YET'}**", f"- {j['roster_addition_risk']}",'','## Snapshot audit','', '| Division | Saved ratings | Existing nonzero roster adjustments | Double-counting warning |','|---|---:|---:|---|']
    for div,item in a['ratings'].items():
        v=item.get('preseason_roster_adjustment',{})
        lines.append(f"| {div} | {item.get('rows','missing')} | {v.get('nonzero_rows','unknown')} | {item.get('double_counting_risk','unknown')} |")
    lines+=['','## Research forecast archives','', '| File | Found | Rows | Timestamp field |','|---|---|---:|---|']
    for k,v in a['prospective_inputs'].items():lines.append(f"| {k} | {v['exists']} | {v.get('rows','—')} | {v.get('time_column','—')} |")
    lines+=['','## Planned sensitivity grid (not executed)','']
    for k,values in PARAMS.items():lines.append(f"- **{k}:** {', '.join(map(str,values))}")
    lines+=['','## Data requirements before calling any variant better','', '- Historical game outcomes and source IDs, deduplicated.', '- As-of pregame baseline inputs, created before the corresponding tipoff.', '- Season-correct roster/player participation known at each relevant prediction timestamp.', '- Neutral/home/away venue status explicitly verified; never assume unknown means home.', '- Season-separated train/validation/test with team/opponent schedule coverage.', '- Compare variants on identical games; report MAE and win accuracy by season/venue and uncertainty.', '- Guard against using official saved preseason roster adjustments twice.', '- Do not infer an optimal HCA, ridge, cap, blending, or cold-start prior from a single current snapshot.', '', '## Output safety','', 'This run is a diagnostic only. It does not automatically fit model variants or publish a new ranking.','']
    return '\n'.join(lines)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--output-dir',default='data/calibration_readiness_v112');args=ap.parse_args()
    root=Path(args.repo_root).resolve();out=Path(args.output_dir)
    if not out.is_absolute():out=root/out
    a={'version':112,'created_utc':datetime.now(timezone.utc).isoformat(),'status':'RESEARCH_ONLY_CALIBRATION_READINESS','production_modified':False,'rating_engine':structural_audit(root),'ratings':{div:rating_snapshot(root,div) for div in DIVS}, 'prospective_inputs':{k:csv_summary(root/v,'existing_archive') for k,v in TARGETS.items() if k.endswith(('forecasts','results','pairs'))},'auxiliary_inputs':{k:{'exists':(root/v).exists(),'path':v} for k,v in TARGETS.items() if k.endswith('summary')},'historical_file_manifest':discover(root)}
    a['decision']=judge(a)
    out.mkdir(parents=True,exist_ok=True)
    (out/'summary.json').write_text(json.dumps(a,indent=2)+'\n',encoding='utf-8')
    (out/'report.md').write_text(markdown(a),encoding='utf-8')
    print(json.dumps({'version':112,'status':a['status'],'historical_tuning_performed':False,'reports':[str(out/'summary.json'),str(out/'report.md')],'decision':a['decision']},indent=2))
if __name__=='__main__':main()

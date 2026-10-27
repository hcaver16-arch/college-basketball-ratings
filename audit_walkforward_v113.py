#!/usr/bin/env python3
"""Courtside V113: read-only historical archive inventory and walk-forward audit.
Only writes to data/walkforward_audit_v113; never modifies source data.
"""
import argparse, csv, gzip, hashlib, json, re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 140_000_000
MAX_ROWS = 220_000
SEASON = re.compile(r'20\d{2}[-_](?:20)?\d{2}')
SOURCE_EXTS = {'.csv', '.gz', '.json', '.jsonl', '.parquet'}
GAME_ID = ('game_id', 'event_id', 'espn_game_id', 'id')
START = ('game_start_utc','start_utc','start_time_utc','tipoff_utc','game_datetime_utc','date_utc','game_date','date')
OBSERVED = ('forecast_created_utc','paired_created_utc','snapshot_created_utc','as_of_utc','as_of','collected_utc','retrieved_utc','created_at','generated_at_utc')
VENUE = ('neutral','neutral_site','is_neutral','venue_type','home_away','home_away_status')
HOME = ('home_id','home_team_id','home_team')
AWAY = ('away_id','away_team_id','away_team')
OUTCOME = ('home_score','away_score','actual_home_margin','home_points','away_points')
DIVISION = ('division','league','sport')
ROSTER = ('player_id','athlete_id','player_name','returning_minutes_pct','prior_team_id','transfer_origin')
MODEL = ('predicted_home_margin','predicted_margin','forecast_created_utc','model_id','home_rating')

def pick(columns, candidates):
    lookup = {x.strip().lower(): x for x in columns}
    return next((lookup[c] for c in candidates if c in lookup), None)

def dt_parse(value):
    s = str(value or '').strip()
    if not s:
        return None
    try:
        if s.endswith('Z'): s = s[:-1] + '+00:00'
        d = datetime.fromisoformat(s)
        if d.tzinfo is None: return None  # cannot prove UTC for naive timestamps
        return d.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None

def category(path, fields):
    p = str(path).lower()
    cols = {s.lower() for s in fields}
    if any(c in cols for c in MODEL): return 'forecast_or_model_snapshot'
    if any(c in cols for c in ROSTER) or 'roster' in p or 'transfer' in p: return 'roster_or_player'
    if pick(fields, GAME_ID) and pick(fields, OUTCOME): return 'game_results_or_schedule'
    if pick(fields, START) and pick(fields, HOME) and pick(fields, AWAY): return 'game_results_or_schedule'
    if 'rating' in p or 'power' in p: return 'ratings_or_priors'
    return 'other_research'

def inspect_csv(path):
    opening = gzip.open if path.suffix.lower() == '.gz' else open
    result = {'columns':[], 'rows_scanned':0, 'truncated_rows':False, 'invalid_csv':None}
    try:
        with opening(path, 'rt', encoding='utf-8-sig', errors='replace', newline='') as f:
            rd = csv.DictReader(f)
            cols = rd.fieldnames or []
            result['columns'] = cols
            gid, start, stamp, venue = (pick(cols, opts) for opts in (GAME_ID, START, OBSERVED, VENUE))
            div = pick(cols, DIVISION)
            states = Counter()
            games = set()
            duplicate = 0
            divs = Counter()
            seasons = Counter()
            examples = []
            for ix, row in enumerate(rd):
                if ix >= MAX_ROWS:
                    result['truncated_rows'] = True
                    break
                result['rows_scanned'] += 1
                if div and row.get(div): divs[row[div]] += 1
                if row.get('season'): seasons[row['season']] += 1
                elif row.get('Season'): seasons[row['Season']] += 1
                if gid:
                    g = str(row.get(gid,'')).strip()
                    if g:
                        # Duplicates may represent multiple model variants or repeat snapshots; review rather than delete.
                        if g in games: duplicate += 1
                        games.add(g)
                if venue:
                    v = str(row.get(venue,'')).strip().lower()
                    states['venue_present' if v and v not in {'unknown','nan','none','null','?'} else 'venue_unknown'] += 1
                else: states['venue_field_absent'] += 1
                if start:
                    d0 = dt_parse(row.get(start))
                    states['tipoff_tz_verified' if d0 else 'tipoff_tz_unverified'] += 1
                if stamp:
                    d1 = dt_parse(row.get(stamp))
                    states['asof_tz_verified' if d1 else 'asof_tz_unverified'] += 1
                if start and stamp:
                    if d0 and d1:
                        states['asof_before_tipoff' if d1 < d0 else 'asof_at_or_after_tipoff'] += 1
                        if d1 >= d0 and len(examples) < 5: examples.append({'row':ix+2,'game_id':row.get(gid,'') if gid else ''})
                    else: states['timing_unverifiable'] += 1
            result.update({'id_field':gid,'tipoff_field':start,'asof_field':stamp,'venue_field':venue,
                'division_field':div,'division_counts':dict(divs.most_common(8)),'season_counts':dict(seasons.most_common(8)),
                'distinct_game_ids':len(games) if gid else None,'repeated_game_id_rows':duplicate if gid else None,
                'checks':dict(states),'post_tipoff_examples':examples})
    except (OSError, csv.Error, UnicodeError, EOFError) as e: result['invalid_csv']=str(e)[:250]
    return result

def scan(root, out, max_files):
    files = []
    excluded = {'.git','.venv','venv','node_modules','__pycache__','.next','dist','build'}
    for p in root.rglob('*'):
        if not p.is_file() or any(part in excluded for part in p.relative_to(root).parts): continue
        if p.is_relative_to(out): continue
        rel = p.relative_to(root)
        if p.suffix.lower() not in SOURCE_EXTS: continue
        # Keep focus on likely data, but don't omit top-level archives.
        if 'data' not in rel.parts and not any(word in str(rel).lower() for word in ('histor','archive','backtest','roster','research','snapshot')): continue
        files.append(p)
    files.sort(key=lambda p: str(p.relative_to(root)))
    over_limit = len(files) > max_files
    return files[:max_files], over_limit

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',default='.')
    ap.add_argument('--output',default='data/walkforward_audit_v113')
    ap.add_argument('--max-files',type=int,default=1500)
    args=ap.parse_args()
    root=Path(args.root).resolve(); out=(root / args.output).resolve()
    if not out.is_relative_to(root): raise SystemExit('Output must be inside repository')
    if not (root / '.git').exists(): print('WARNING: repository .git not found; scanning provided root anyway')
    files, limited=scan(root,out,args.max_files)
    inventory=[]; cats=Counter(); evidence=Counter(); divisions=defaultdict(Counter)
    for p in files:
        rel=str(p.relative_to(root)); size=p.stat().st_size
        record={'path':rel,'size_bytes':size,'extension':p.suffix.lower(),'inferred_season':(SEASON.search(rel).group() if SEASON.search(rel) else None)}
        if size > MAX_BYTES:
            record.update({'status':'skipped_oversize','classification':'unknown'}); evidence['skipped_oversize']+=1
        elif p.suffix.lower()=='.csv' or p.name.lower().endswith('.csv.gz'):
            detail=inspect_csv(p); record.update(detail); record['classification']=category(p, detail.get('columns',[]))
            record['status']='parse_error' if detail.get('invalid_csv') else 'scanned'
            c=detail.get('checks',{})
            if c.get('asof_before_tipoff'): evidence['rows_timestamped_before_tipoff']+=c['asof_before_tipoff']
            if c.get('asof_at_or_after_tipoff'): evidence['rows_timestamped_at_or_after_tipoff']+=c['asof_at_or_after_tipoff']
            if c.get('timing_unverifiable'): evidence['rows_unverifiable_timing']+=c['timing_unverifiable']
            if detail.get('tipoff_field') and detail.get('asof_field'): evidence['files_with_both_timestamps']+=1
            for d,n in detail.get('division_counts',{}).items(): divisions[d][record['classification']]+=n
        else:
            record.update({'status':'metadata_only_not_parsed','classification':category(p,[]),
                'note':'JSON/Parquet metadata only; contents and timestamps not verified'})
        cats[record['classification']]+=1
        inventory.append(record)
    # Focused, read-only discovery of V105 paths; do not guess fixed directory from version number.
    roster105=[i['path'] for i in inventory if 'v105' in i['path'].lower()]
    missing=[]
    for path in ('data/prospective/2026-27/forecasts.csv','data/prospective/2026-27/results.csv',
                 'data/prospective/2026-27/roster_pairs_v109.csv'):
        if not (root/path).is_file(): missing.append(path)
    blocking=[
        'No verified historical input-availability timestamps or replayable per-game as-of ratings established by file inventory alone',
        'Competition venue requires source verification: populated Neutral values are not proof they are accurate',
        'Roster snapshots must be specific to the season and collected before each forecast, not just labeled with a season',
        'Separate chronological train/validation/test partitions and identical-game evaluation remain to be implemented',
    ]
    summary={'version':113,'generated_utc':datetime.now(timezone.utc).isoformat(),
      'status':'READ_ONLY_WALKFORWARD_ARCHIVE_INVENTORY','production_modified':False,
      'file_count_scanned':len(inventory),'file_limit_reached':limited,
      'classification_counts':dict(cats),'evidence_counts':dict(evidence),
      'division_rows_by_category':{k:dict(v) for k,v in divisions.items()},
      'v105_named_paths':roster105[:50],'known_prospective_files_missing':missing,
      'decision':{'historical_walkforward_validated':False,'hyperparameter_tuning_allowed':False,
        'notes':'Pre-tipoff timestamps alone do not establish complete upstream data provenance or prevent leakage',
        'blockers':blocking},
      'limits':['Max 1500 files; 220000 CSV rows per file; 140 MB/file by default',
        'JSON and Parquet are inventoried by filename/size only; content not validated',
        'CSV timestamps require explicit timezone; date-only or timezone-naive values are unverifiable',
        'Repeated game IDs may legitimately reflect forecast versions; not automatically data errors',
        'Rows are grouped by fields and filenames, not authoritative NCAA classification'],
      'output_paths':['data/walkforward_audit_v113/summary.json','data/walkforward_audit_v113/inventory.json','data/walkforward_audit_v113/report.md']}
    out.mkdir(parents=True,exist_ok=True)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (out/'inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
    lines=['# Courtside V113 — Historical walk-forward audit','',
      '**READ-ONLY on research inputs. No ratings, forecasts, site, or model files changed.**','',
      '## Inventory overview','',f'- Files scanned: **{len(inventory)}**'+(' (limit reached)' if limited else ''),
      f'- Files with both timestamp fields: **{evidence["files_with_both_timestamps"]}**',
      f'- Rows with parsed as-of before tipoff: **{evidence["rows_timestamped_before_tipoff"]}**',
      f'- Rows with as-of at or after tipoff: **{evidence["rows_timestamped_at_or_after_tipoff"]}**',
      f'- Unverifiable date comparisons: **{evidence["rows_unverifiable_timing"]}**','',
      '## Archive types','', '| Inferred category | Files |','|---|---:|']
    lines += [f'| {name} | {count} |' for name,count in sorted(cats.items())]
    lines += ['','## V105 locations found','']
    lines += [f'- `{p}`' for p in roster105[:30]] or ['- No V105-named data files detected in repository scan']
    lines += ['','## CSV files with timestamp evidence','', '| File | Rows | Pregame | After/at tipoff | Unverifiable |','|---|---:|---:|---:|---:|']
    for rec in inventory:
        if rec.get('tipoff_field') and rec.get('asof_field'):
            c=rec.get('checks',{})
            lines.append(f'| `{rec["path"]}` | {rec.get("rows_scanned",0)} | {c.get("asof_before_tipoff",0)} | {c.get("asof_at_or_after_tipoff",0)} | {c.get("timing_unverifiable",0)} |')
    lines += ['','## Missing known prospective archives','']
    lines += [f'- `{p}`' for p in missing] or ['- All three known V97/V109 CSV files are present']
    lines += ['','## Decision','', '**Historical hyperparameter tuning is NOT authorized by this audit.**','']
    lines += [f'- {b}' for b in blocking]
    lines += ['','## Next actions','',
      '1. Inspect `inventory.json` for historical game tables and exact season fields.',
      '2. Identify raw event timestamps plus archival acquisition timestamps for every required rating feature.',
      '3. Establish a validated source for home/away/neutral site flags.',
      '4. Rebuild past ratings progressively from games completed strictly before each scheduled tipoff.',
      '5. Only then evaluate frozen model variants on held-out periods and identical matchups.','',
      '**Scope:** JSON and Parquet contents are not parsed; the inventory alone cannot prove leakage-free replay.']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'status':summary['status'],'files_scanned':len(inventory),'v105_paths':len(roster105),'output':str(out)},indent=2))
if __name__=='__main__': main()

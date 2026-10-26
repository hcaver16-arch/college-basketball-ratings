"""Read-only roster archive coverage audit, compatible with Courtside v24-v39 files.

Output under data/roster_audit_v102; never modifies raw roster/player archives.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

SPORTS = ('mens-college-basketball', 'womens-college-basketball')


def load(root, sport, suffix):
    p = root / f'{sport}_{suffix}.csv.gz'
    if not p.is_file():
        return pd.DataFrame()
    return pd.read_csv(p, dtype={'Team ID': str, 'Player ID': str}, low_memory=False)


def summarize(root, sport, directory=None):
    status = load(root, sport, 'collection_status')
    curr = load(root, sport, 'current_rosters')
    prev = load(root, sport, 'previous_rosters')
    stats = load(root, sport, 'previous_stats')
    for df in (status, curr, prev, stats):
        if not df.empty and 'Team ID' in df:
            df['Team ID'] = df['Team ID'].astype(str).str.strip()
    if directory is None:
        # Offline fallback is NOT proof of complete D1 directory coverage.
        ids = set()
        for df in (status, curr, prev, stats):
            if 'Team ID' in df:
                ids.update(df['Team ID'].dropna().tolist())
        directory = pd.DataFrame({'Team ID': sorted(ids), 'Team': sorted(ids)})
        directory_source = 'archive_only_INCOMPLETE_DENOMINATOR'
    else:
        directory_source = 'live_espn_d1_directory'
    if 'Team ID' not in directory:
        raise ValueError('Directory missing Team ID')
    directory = directory.copy()
    directory['Team ID'] = directory['Team ID'].astype(str).str.strip()
    directory = directory.drop_duplicates('Team ID')
    def counts(frame):
        if frame.empty or 'Team ID' not in frame:
            return {}
        if 'Player ID' in frame:
            clean = frame.dropna(subset=['Player ID'])
            return clean.groupby('Team ID')['Player ID'].nunique().to_dict()
        return frame.groupby('Team ID').size().to_dict()
    current_ct, previous_ct, stats_ct = (counts(x) for x in (curr, prev, stats))
    status_lookup = {}
    if 'Team ID' in status:
        status_lookup = {r['Team ID']: r for r in status.drop_duplicates('Team ID', keep='last').to_dict('records')}
    output = []
    for r in directory.to_dict('records'):
        tid = str(r['Team ID']); st = status_lookup.get(tid, {})
        current = current_ct.get(tid, 0); prior = previous_ct.get(tid, 0); productions = stats_ct.get(tid, 0)
        state = str(st.get('state') or 'unattempted').strip()
        parsed = pd.to_numeric(st.get('Game box scores parsed'), errors='coerce')
        discovered = pd.to_numeric(st.get('Completed games in feed'), errors='coerce')
        box_coverage = bool(pd.notna(parsed) and pd.notna(discovered) and discovered > 0 and parsed == discovered)
        # A 'collected' state indicates an endpoint was traversed, NOT verified roster identity or year.
        archive_ready = bool(current > 0 and prior > 0 and productions > 0 and box_coverage and state == 'collected')
        reasons=[]
        if not current: reasons.append('missing_current_roster')
        if not prior: reasons.append('missing_prior_roster')
        if not productions: reasons.append('missing_prior_player_stats')
        if not box_coverage: reasons.append('boxscore_coverage_unverified_or_partial')
        if state != 'collected': reasons.append('collection_state_'+state)
        output.append({'division': sport, 'team_id':tid, 'team':r.get('Team') or st.get('Team') or tid,
                       'state':state, 'current_roster_players':int(current), 'prior_roster_players':int(prior),
                       'prior_player_stats_rows':int(productions), 'boxscores_parsed':None if pd.isna(parsed) else int(parsed),
                       'completed_games_in_feed':None if pd.isna(discovered) else int(discovered),
                       'archive_ready_unverified':archive_ready, 'issues':';'.join(reasons),
                       'details':str(st.get('details') or '')[:230]})
    n=len(output)
    return {'division':sport,'directory_source':directory_source,'directory_teams':n,
            'teams_with_current_roster':sum(x['current_roster_players']>0 for x in output),
            'teams_with_prior_roster':sum(x['prior_roster_players']>0 for x in output),
            'teams_with_prior_player_stats':sum(x['prior_player_stats_rows']>0 for x in output),
            'teams_marked_collected':sum(x['state']=='collected' for x in output),
            'archive_ready_unverified':sum(x['archive_ready_unverified'] for x in output),
            'missing_or_partial':sum(not x['archive_ready_unverified'] for x in output),
            'notes':['Archive-ready means saved roster and stats coverage exists, not verified 2026-27 roster identity.',
                     'ESPN season labels and completeness can be inaccurate; manual point-in-time verification is separate.',
                     'Missing/partial teams are listed in CSV and JSON. Ratings are untouched.'], 'teams':output}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data', default='data')
    parser.add_argument('--out', default='data/roster_audit_v102')
    parser.add_argument('--offline', action='store_true', help='Use archived team IDs only (incomplete denominator)')
    args=parser.parse_args()
    root=Path(args.data); out=Path(args.out);out.mkdir(parents=True, exist_ok=True)
    results=[]
    for sport in SPORTS:
        directory = None
        if not args.offline:
            # Reuse the deployed collector's exact D1 directory query.
            from archive_roster_batch import directory as fetch_directory
            directory=fetch_directory(sport)
            if directory.empty: raise RuntimeError('Empty ESPN team directory for '+sport)
        report=summarize(root,sport,directory)
        results.append(report)
        pd.DataFrame(report['teams']).to_csv(out/f'{sport}_teams.csv', index=False)
        with (out/f'{sport}_status.json').open('w') as f: json.dump({k:v for k,v in report.items() if k!='teams'},f,indent=2)
        print(f"{sport}: {report['archive_ready_unverified']}/{report['directory_teams']} archive-ready (unverified); missing/partial {report['missing_or_partial']}",flush=True)
    with (out/'summary.json').open('w') as f:
        json.dump({'version':102,'checked_at_utc':datetime.now(timezone.utc).isoformat(),
                   'divisions':[{k:v for k,v in x.items() if k!='teams'} for x in results]},f,indent=2)

if __name__=='__main__': main()

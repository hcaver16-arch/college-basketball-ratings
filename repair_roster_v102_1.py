"""Targeted ESPN roster repair for West Florida (both divisions) and Navy women.

No invented players, no automatic exemptions, and no modification of power ratings.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests
from archive_roster_batch import read, write, merge
from roster_tracking import read_roster
from player_stats_import import (fetch_prior_stats, games_from_schedule,
                                 parse_boxscore, HEADERS)

TARGETS = [('mens-college-basketball', '2697', 'West Florida Argonauts'),
           ('womens-college-basketball', '2697', 'West Florida Argonauts'),
           ('womens-college-basketball', '2426', 'Navy Midshipmen')]
API = 'https://site.api.espn.com/apis/site/v2/sports/basketball'
SUMMARY = 'https://site.web.api.espn.com/apis/site/v2/sports/basketball'


def check_games(sport, tid):
    """Diagnose the exact prior-season ESPN game IDs that cannot be parsed."""
    r = requests.get(f'{API}/{sport}/teams/{tid}/schedule',
                     params={'season': 2026}, headers=HEADERS, timeout=25)
    r.raise_for_status()
    games = games_from_schedule(r.json())
    results = []
    for gid in games:
        try:
            response = requests.get(f'{SUMMARY}/{sport}/summary',
                                    params={'event': gid}, headers=HEADERS, timeout=25)
            response.raise_for_status()
            count = len(parse_boxscore(response.json(), tid, gid))
            results.append({'game_id': gid, 'parsed_players': count,
                            'state': 'parsed' if count else 'missing_player_boxscore'})
        except (requests.RequestException, ValueError, KeyError) as exc:
            results.append({'game_id': gid, 'state': 'request_or_parse_error',
                            'error': f'{type(exc).__name__}: {exc}'[:200]})
    return {'completed_game_ids': len(games), 'parsed_games': sum(x['state']=='parsed' for x in results),
            'unparsed_games': [x for x in results if x['state']!='parsed']}


def repair(sport, tid, label, apply, audit_games=True):
    record = {'division': sport, 'team_id': tid, 'team': label, 'attempted_at': datetime.now(timezone.utc).isoformat(),
              'mode': 'write_verified_source_data' if apply else 'read_only_diagnostic',
              'source': 'ESPN unofficial API', 'current_season': 2027, 'previous_season': 2026,
              'warnings': [], 'changes': []}
    old = {k: read(k, sport) for k in ('previous_rosters', 'current_rosters', 'previous_stats', 'collection_status')}
    selected = pd.DataFrame([{'Team ID': tid, 'Team': label}])
    current, prior = pd.DataFrame(), pd.DataFrame()
    for season, key in ((2026, 'previous_rosters'), (2027, 'current_rosters')):
        try:
            frame = read_roster(sport, tid, label, season)
            record[f'{key}_fetched_players'] = int(len(frame))
            if season == 2026: prior = frame
            else: current = frame
        except Exception as exc:
            record[f'{key}_fetched_players'] = 0
            record['warnings'].append(f'{key} request failed: {type(exc).__name__}: {exc}'[:230])
    if audit_games:
        try: record['boxscore_audit'] = check_games(sport, tid)
        except Exception as exc:
            record['warnings'].append(f'Game-by-game diagnostic failed: {type(exc).__name__}: {exc}'[:230])
    try:
        stats, diagnostics, errs = fetch_prior_stats(sport, selected, season=2026, max_games=45, max_workers=3)
        d = diagnostics.iloc[0].to_dict() if not diagnostics.empty else {}
        total = pd.to_numeric(d.get('Completed games in feed'), errors='coerce')
        parsed = pd.to_numeric(d.get('Game box scores parsed'), errors='coerce')
        record['prior_stats_fetched_players'] = int(len(stats))
        record['completed_games'] = int(total) if pd.notna(total) else None
        record['parsed_games'] = int(parsed) if pd.notna(parsed) else None
        record['warnings'].extend(str(x)[:200] for x in errs[:5])
    except Exception as exc:
        stats = pd.DataFrame(); total = parsed = float('nan')
        record['warnings'].append(f'Prior statistics request failed: {type(exc).__name__}: {exc}'[:230])
    # Archive good partial sources, but never label fully ready with missing games/roster.
    full = (not current.empty and not prior.empty and not stats.empty and pd.notna(total)
            and total > 0 and pd.notna(parsed) and int(total) == int(parsed))
    record['fully_collected_from_espn'] = bool(full)
    record['diagnosis'] = ('complete_collection' if full else
                           'espn_roster_unavailable' if current.empty or prior.empty else
                           'prior_boxscore_incomplete' if pd.notna(total) and pd.notna(parsed) and int(total)!=int(parsed) else
                           'missing_or_unverified_historical_player_stats')
    if apply:
        for key, frame in (('previous_rosters', prior), ('current_rosters', current), ('previous_stats', stats)):
            if frame.empty: continue
            required = {'Team ID', 'Player ID'}
            if not required.issubset(frame.columns):
                record['warnings'].append(key + ' missing expected ID columns, not saved')
                continue
            combined = merge(old[key], [frame], ['Team ID', 'Player ID'])
            write(key, sport, combined, ['Team ID', 'Player ID'])
            record['changes'].append(f'{key}: source rows merged, existing rows retained')
        status = old['collection_status']
        row = {}
        if not status.empty and 'Team ID' in status:
            match = status[status['Team ID'].astype(str)==tid]
            if not match.empty: row.update(match.iloc[-1].to_dict())
        row.update({'Team ID': tid, 'Team': label, 'Last audit attempt': record['attempted_at'],
                    'state': 'collected' if full else ('partial' if not current.empty or not prior.empty else 'retry'),
                    'details': 'V102.1 targeted: ' + record['diagnosis'] + '; source data not fabricated'})
        if pd.notna(total): row['Completed games in feed'] = int(total)
        if pd.notna(parsed): row['Game box scores parsed'] = int(parsed)
        if pd.notna(total) and pd.notna(parsed): row['Missing/invalid games'] = max(0, int(total)-int(parsed))
        merged = merge(status, [pd.DataFrame([row])], ['Team ID'])
        write('collection_status', sport, merged, ['Team ID'])
        record['changes'].append('collection_status: diagnostic state updated')
    return record


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--apply', action='store_true', help='Merge fetched source data; default read only')
    p.add_argument('--out', default='data/roster_audit_v102_1')
    p.add_argument('--skip-game-audit', action='store_true')
    args = p.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    results=[]
    for sport, tid, label in TARGETS:
        print(f'Inspecting {sport}: {label} ({tid})', flush=True)
        try: result=repair(sport, tid, label, args.apply, not args.skip_game_audit)
        except Exception as exc:
            result={'division':sport,'team_id':tid,'team':label,'diagnosis':'unexpected_failure',
                    'warnings':[f'{type(exc).__name__}: {exc}'[:300]]}
        results.append(result)
        print(f"  {result.get('diagnosis')}: {result.get('warnings', [])[:1]}",flush=True)
    report={'version':'102.1','generated_at':datetime.now(timezone.utc).isoformat(),
            'read_only':not args.apply, 'note':'Data-source failures are preserved, not excused as complete.',
            'teams':results}
    (out/'targeted_report.json').write_text(json.dumps(report, indent=2, default=str)+'\n')
    with (out/'summary.md').open('w') as f:
        f.write('# Courtside V102.1 targeted roster diagnosis\n\n')
        f.write('| Team | Division | Diagnosis | 2026 roster | 2027 roster | Parsed / completed |\n')
        f.write('|---|---|---|---:|---:|---|\n')
        for r in results:
            f.write(f"| {r['team']} | {r['division']} | {r.get('diagnosis','error')} | {r.get('previous_rosters_fetched_players','—')} | {r.get('current_rosters_fetched_players','—')} | {r.get('parsed_games','—')} / {r.get('completed_games','—')} |\n")
        f.write('\nCheck targeted_report.json for missing ESPN game IDs and source errors.\n')
    print((out/'summary.md').read_text())

if __name__ == '__main__': main()

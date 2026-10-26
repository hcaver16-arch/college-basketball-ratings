"""Courtside V99: read-only prospective pipeline diagnostics.

Fetches ESPN schedules live, checks on-disk rating metadata and V97's
append-only archive; writes an independent health report. It never edits V97.
"""
from __future__ import annotations
import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from prospective_archive_v97 import SPORTS, parse_dt, scoreboard, read_csv, FIELDS, RESULT_FIELDS, load_official

ET = ZoneInfo('America/New_York')
SEVERITY = {'ok': 0, 'info': 0, 'warning': 1, 'critical': 2}


def check_division(root, season, division, now, games, forecasts, results, days=2):
    issues=[]
    def issue(level, code, message, count=0, examples=None):
        issues.append({'severity':level,'code':code,'message':message,'count':count,'examples':(examples or [])[:8]})

    upcoming=[g for g in games.values() if not g['final'] and (parse_dt(g['game_start_utc']) or now) > now]
    imminent=[g for g in upcoming if parse_dt(g['game_start_utc']) <= now+timedelta(hours=12)]
    soon=[g for g in upcoming if parse_dt(g['game_start_utc']) <= now+timedelta(hours=3)]
    completed=[g for g in games.values() if g['final'] and parse_dt(g['game_start_utc']) < now-timedelta(hours=8)]
    division_forecasts=[f for f in forecasts if f['division']==division and f['model_id']=='official_saved_v97']
    forecast_map={f['game_id']:f for f in division_forecasts}
    result_ids={r['game_id'] for r in results if r['division']==division and r.get('status')=='Final'}

    # V97 only creates predictions up to 42h out, minimum 30 minutes before tipoff.
    missing=[g for g in imminent if g['game_id'] not in forecast_map]
    urgent=[g for g in soon if g['game_id'] not in forecast_map]
    if urgent:
        issue('critical','MISSING_IMMINENT_FORECASTS',f'{len(urgent)} games within three hours lack a locked official forecast',len(urgent),[x['away_team']+' @ '+x['home_team'] for x in urgent])
    elif missing:
        issue('warning','MISSING_UPCOMING_FORECASTS',f'{len(missing)} games within 12 hours lack a locked official forecast',len(missing),[x['away_team']+' @ '+x['home_team'] for x in missing])

    unrecorded=[g for g in completed if g['game_id'] in forecast_map and g['game_id'] not in result_ids]
    if unrecorded:
        issue('warning','MISSING_FINAL_RESULTS',f'{len(unrecorded)} ESPN-final games with locked forecasts lack archived results (8h+ since start)',len(unrecorded),[x['game_id'] for x in unrecorded])

    bad=[]
    for f in division_forecasts:
        p=parse_dt(f.get('forecast_created_utc'));t=parse_dt(f.get('game_start_utc'));s=parse_dt(f.get('ratings_snapshot_utc'))
        if not (p and t and s and s<=p<t):bad.append(f.get('game_id'))
    if bad:
        issue('critical','INVALID_PREGAME_TIMESTAMPS',f'{len(bad)} official forecasts have invalid/pre-tip timestamps',len(bad),bad)
    counts=Counter(f['game_id'] for f in division_forecasts)
    duplicate=[k for k,v in counts.items() if v>1]
    if duplicate:issue('critical','DUPLICATE_FORECASTS','Official game IDs recorded more than once',len(duplicate),duplicate)

    sport=SPORTS[0] if division=='mens' else SPORTS[1]
    rating,error=load_official(sport,root,now)
    if error:
        # Off-season metadata can be stale without harm; imminent games cannot.
        level='critical' if imminent else 'info'
        issue(level,'RATINGS_NOT_READY',error,len(imminent))
    else:
        unmatched=[g for g in imminent if g['home_id'] not in rating['ratings'] or g['away_id'] not in rating['ratings']]
        if unmatched:
            issue('critical','UNKNOWN_RATED_TEAMS',f'{len(unmatched)} imminent games reference teams absent from saved ratings',len(unmatched),[x['away_team']+' @ '+x['home_team'] for x in unmatched])

    # We intentionally don't treat an empty scoreboard as an error unless the API itself failed.
    if not games: issue('info','NO_SCHEDULED_GAMES','No games returned for the inspected days; normal before the season')
    health='critical' if any(i['severity']=='critical' for i in issues) else 'warning' if any(i['severity']=='warning' for i in issues) else 'ok'
    return {'status':health, 'games_seen':len(games),'upcoming_12h':len(imminent),'upcoming_3h':len(soon),'official_forecasts_total':len(division_forecasts),'final_results_total':sum(r['division']==division for r in results),'issues':issues}


def run(root,season,now,session=None):
    folder=root/'data'/'prospective'/season
    forecasts=read_csv(folder/'forecasts.csv',FIELDS)
    results=read_csv(folder/'results.csv',RESULT_FIELDS)
    today=now.astimezone(ET).date()
    reports={}; fetch_issues=[]
    for sport in SPORTS:
        div='mens' if sport.startswith('mens') else 'womens'
        combined={}
        for offset in range(-3,3):
            d=today+timedelta(days=offset)
            try: combined.update(scoreboard(sport,d,session=session))
            except Exception as exc: fetch_issues.append({'division':div,'date':d.isoformat(),'error':str(exc)})
        reports[div]=check_division(root,season,div,now,combined,forecasts,results)
    if fetch_issues:
        status='critical'
    elif any(r['status']=='critical' for r in reports.values()):status='critical'
    elif any(r['status']=='warning' for r in reports.values()):status='warning'
    else:status='ok'
    result={'version':99,'season':season,'checked_at_utc':now.isoformat(timespec='seconds'),'status':status,'divisions':reports,'scoreboard_fetch_errors':fetch_issues,'notes':['Read-only inspection of saved ratings and immutable V97 records.','Schedule coverage is based on ESPN scoreboard; missing API dates cause critical status.','No completed games or stale preseason ratings are not alerts by themselves.','V97 must run separately; this workflow diagnoses but cannot guarantee every forecast is captured.']}
    destination=folder/'health_v99.json';destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--season',default='2026-27');p.add_argument('--fail-on-critical',action='store_true');a=p.parse_args()
    x=run(Path(a.root),a.season,datetime.now(timezone.utc))
    print(json.dumps(x,indent=2))
    if a.fail_on_critical and x['status']=='critical':raise SystemExit(2)
if __name__=='__main__':main()

"""Compute and archive historical-margin college-basketball ratings, separately by division.
Use before-season history as priors; do not infer roster-based numerical impacts.
"""
import argparse
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
import pandas as pd
import requests
from rating_engine import calculate_power, make_combined

ROOT=Path(__file__).resolve().parent/'data'/'ratings'
SPORTS=['mens-college-basketball','womens-college-basketball']
COLUMNS=['Game ID','Date','Away','Home','Away ID','Home ID','Venue','Status','Away score','Home score']

def days(a,b):
    while a<=b:
        yield a
        a+=timedelta(days=1)

def request_date(sport,day):
    url=f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/scoreboard'
    resp=requests.get(url,params={'dates':day.strftime('%Y%m%d'),'groups':'50','limit':500},timeout=30,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
    resp.raise_for_status()
    payload=resp.json()
    events=payload.get('events')
    if not isinstance(events,list) or len(events)>=500:
        raise ValueError(f'Invalid/truncated feed on {day}: {len(events) if isinstance(events,list) else "missing"}')
    out=[]
    for e in events:
        c=(e.get('competitions') or [{}])[0]
        teams=c.get('competitors') or []
        h=next((x for x in teams if x.get('homeAway')=='home'),None)
        a=next((x for x in teams if x.get('homeAway')=='away'),None)
        if h is None or a is None:continue
        status=(e.get('status') or {}).get('type') or (c.get('status') or {}).get('type') or {}
        final=bool(status.get('completed'))
        def score(t):
            s=t.get('score')
            if isinstance(s,dict):s=s.get('value',s.get('displayValue'))
            try:return int(float(s))
            except (TypeError,ValueError):return None
        day_str=pd.to_datetime(e.get('date'),utc=True,errors='coerce')
        if pd.isna(day_str):continue
        name=lambda t:(t.get('team') or {}).get('displayName') or (t.get('team') or {}).get('name') or ''
        out.append({'Game ID':str(e.get('id','')),'Date':str(day_str.tz_convert('America/New_York').date()),
          'Away':name(a),'Home':name(h),'Away ID':str((a.get('team') or {}).get('id','')),
          'Home ID':str((h.get('team') or {}).get('id','')),'Venue':'Neutral' if c.get('neutralSite') else 'Home',
          'Status':'Final' if final else 'Scheduled', 'Away score':score(a) if final else None,'Home score':score(h) if final else None})
    return out

def fetch(sport, day_list):
    records=[];fail=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(request_date,sport,d):d for d in day_list}
        for f in as_completed(futures):
            try:records.extend(f.result())
            except Exception as exc:fail.append(f'{futures[f]}: {exc}')
    return pd.DataFrame(records,columns=COLUMNS),fail

def load_cache(path):
    if not path.exists():return pd.DataFrame(columns=COLUMNS)
    frame=pd.read_csv(path,compression='gzip',dtype={'Game ID':str,'Home ID':str,'Away ID':str})
    return frame.reindex(columns=COLUMNS)

def write_csv(frame,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    frame.to_csv(tmp,index=False,compression='gzip')
    os.replace(tmp,path)

def run(sport, asof):
    root=ROOT/sport
    root.mkdir(parents=True,exist_ok=True)
    previous_path=root/'history_2025-26.csv.gz'
    previous=load_cache(previous_path)
    previous_ready=(len(previous[previous['Status']=='Final'])>=1000)
    if not previous_ready:
        prior,fail=fetch(sport,list(days(date(2025,11,1),date(2026,4,7))))
        if fail:raise RuntimeError(f'Historical fetch incomplete: {len(fail)} errors; {fail[:2]}')
        if len(prior[prior['Status']=='Final'])<1000:raise RuntimeError('Too few historical finals; archive not replaced')
        previous=prior.drop_duplicates('Game ID')
        write_csv(previous,previous_path)
    prior_rating,prior_stats=calculate_power(previous)
    if prior_rating.empty:raise RuntimeError('Historical ratings unavailable')
    active_path=root/'season_2026-27.csv.gz'
    current=load_cache(active_path)
    first=date(2026,11,1)
    last=min(asof,date(2027,4,12))
    if last>=first:
        # Pick up missed days after an outage, rechecking recent scores for corrections.
        existing_dates=set(current['Date'].dropna().astype(str).tolist())
        start_recent=last-timedelta(days=6)
        refresh=[day for day in days(first,last) if day>=start_recent or str(day) not in existing_dates]
        new,fail=fetch(sport,refresh)
        if fail:raise RuntimeError(f'Current-season fetch incomplete: {len(fail)} errors; {fail[:2]}')
        current=pd.concat([current,new],ignore_index=True).drop_duplicates('Game ID',keep='last')
        write_csv(current,active_path)
    current_rating,current_stats=calculate_power(current)
    combined=make_combined(prior_rating,current_rating,{})
    combined.insert(0,'Rank',range(1,len(combined)+1))
    combined['Division']=sport
    combined['As of UTC']=datetime.now(timezone.utc).isoformat(timespec='seconds')
    combined['Rating source']='2025-26 game margins + 2026-27 game margins (no roster adjustments)'
    # Record a daily snapshot, replacing a previous snapshot for the same UTC calendar date.
    snapshot_path=root/'latest.csv.gz'
    history_path=root/'history.csv.gz'
    write_csv(combined,snapshot_path)
    if history_path.exists():
        snapshots=pd.read_csv(history_path,compression='gzip',dtype={'Team ID':str})
        snapshots=snapshots[snapshots['Snapshot date']!=str(asof)]
    else:snapshots=pd.DataFrame()
    daily=combined[['Team ID','Team','Rank','Current power','Preseason rating','On-court rating','Games played','Preseason weight']].copy()
    daily.insert(0,'Snapshot date',str(asof))
    all_dates=pd.concat([snapshots,daily],ignore_index=True)
    write_csv(all_dates,history_path)
    details={'division':sport,'snapshot_date':str(asof),'updated_utc':datetime.now(timezone.utc).isoformat(),
      'historical_final_games':int(prior_stats['games']),'current_final_games':int(current_stats['games']),
      'team_count':len(combined),'method':'regularized scoring margins; 2025-26 preseason prior; no automatic roster adjustment',
      'warning':'Season-specific fitting and scale calibration remain experimental; no betting guarantee.'}
    (root/'status.json').write_text(json.dumps(details,indent=2)+'\n')
    print(f'{sport}: {len(combined)} saved ratings, {prior_stats["games"]} historical finals, {current_stats["games"]} current finals, snapshot {asof}',flush=True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--sport',choices=['both']+SPORTS,default='both')
    ap.add_argument('--asof',type=date.fromisoformat,default=date.today())
    args=ap.parse_args()
    failures=[]
    for sport in SPORTS if args.sport=='both' else [args.sport]:
        try:run(sport,args.asof)
        except Exception as exc:
            print(f'FAILED {sport}: {exc}',flush=True)
            failures.append(sport)
    if failures:raise SystemExit(f'No new saved ratings for failed division(s): {failures}')
if __name__=='__main__':main()

"""Immutable first-before-tip prospective forecasts and separate final score evaluation.

Uses the same baseline +/- 3 home-site difference and prospective_roster.evidence_adjustments
as Streamlit Version 36. No dependence on the Streamlit runtime.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import json
import os
import pandas as pd
import requests
from prospective_roster import evidence_adjustments
from saved_roster_data import load_saved_data

ROOT = Path(__file__).resolve().parent / 'data'
SPORTS = ('mens-college-basketball','womens-college-basketball')
FIELDS = ['Division','Game ID','Game start UTC','First forecast UTC','Home ID','Away ID','Home','Away','Venue',
          'Baseline home margin','Roster experimental home margin','Roster eligible','Home retention %',
          'Away retention %','Rating snapshot date','Source','Experimental coefficient']


def utc_now():
    return datetime.now(timezone.utc)


def get_json_day(sport, day):
    url=f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/scoreboard'
    resp=requests.get(url,params={'dates':day.strftime('%Y%m%d'),'groups':'50','limit':500},
        headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'},timeout=30)
    resp.raise_for_status()
    events=resp.json().get('events')
    if not isinstance(events,list) or len(events)>=500:
        raise ValueError(f'Invalid/truncated schedule: {day}')
    return events


def read_gz(path, cols=None):
    if not path.exists():return pd.DataFrame(columns=cols)
    return pd.read_csv(path,compression='gzip',dtype={'Game ID':str,'Home ID':str,'Away ID':str,'Team ID':str})


def save_gz(df,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    df.to_csv(temp,index=False,compression='gzip')
    os.replace(temp,path)


def as_utc(x):
    val=pd.to_datetime(x,utc=True,errors='coerce')
    return val.to_pydatetime() if not pd.isna(val) else None


def parse_event(event):
    comps=event.get('competitions') or []
    if not comps:return None
    comp=comps[0]
    home=next((x for x in comp.get('competitors',[]) if x.get('homeAway')=='home'),None)
    away=next((x for x in comp.get('competitors',[]) if x.get('homeAway')=='away'),None)
    if not home or not away:return None
    start=as_utc(event.get('date'))
    if not start:return None
    status=(event.get('status') or {}).get('type') or (comp.get('status') or {}).get('type') or {}
    def team(x):return x.get('team') or {}
    def score(x):
        v=x.get('score')
        if isinstance(v,dict):v=v.get('value',v.get('displayValue'))
        try:return int(float(v))
        except (TypeError, ValueError):return None
    return {'Game ID':str(event.get('id','')),'Game start UTC':start.isoformat(),
         'Home ID':str(team(home).get('id','')),'Away ID':str(team(away).get('id','')),
         'Home':team(home).get('displayName',''),'Away':team(away).get('displayName',''),
         'Venue':'Neutral' if comp.get('neutralSite') else 'Home',
         'Status':'Final' if status.get('completed') else ('Live' if status.get('state')=='in' else 'Scheduled'),
         'Home score':score(home),'Away score':score(away)}


def fetch_events(sport,now,horizon_days=7):
    # ESPN schedule is queried by local New York calendar day to catch overnight UTC boundaries.
    a=(now-timedelta(days=1)).date();b=(now+timedelta(days=horizon_days)).date()
    days=[a+timedelta(days=i) for i in range((b-a).days+1)]
    events=[]; errors=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        fut={pool.submit(get_json_day,sport,d):d for d in days}
        for f in as_completed(fut):
            try:events.extend(f.result())
            except Exception as exc:errors.append(f'{fut[f]} {exc}')
    if errors:raise RuntimeError('Schedule fetch incomplete: '+'; '.join(errors[:3]))
    rows=[parse_event(e) for e in events]
    return pd.DataFrame([r for r in rows if r and r['Game ID']]).drop_duplicates('Game ID')


def forecast_new_games(schedule,latest,rosters,now,sport,existing_ids):
    rated=latest.copy()
    rated['Team ID']=rated['Team ID'].astype(str)
    lookup=dict(zip(rated['Team ID'],pd.to_numeric(rated['Current power'],errors='coerce')))
    prior,current,totals,_=rosters
    ids=set(schedule['Home ID'].astype(str))|set(schedule['Away ID'].astype(str)) if not schedule.empty else set()
    adjustments=evidence_adjustments(prior,current,totals,ids)
    new=[]
    for g in schedule.to_dict('records'):
        gid=g['Game ID']; start=as_utc(g['Game start UTC'])
        if gid in existing_ids or not start or not now<start or g['Status']!='Scheduled':continue
        h,a=g['Home ID'],g['Away ID']
        hp,ap=lookup.get(h),lookup.get(a)
        if hp is None or ap is None or pd.isna(hp) or pd.isna(ap):continue
        adv=0 if g['Venue']=='Neutral' else 3.0
        baseline=round(float(hp-ap+adv),2)
        eligible=h in adjustments and a in adjustments
        experiment=round(baseline+adjustments[h]['adjustment']-adjustments[a]['adjustment'],2) if eligible else None
        new.append({'Division':sport,'Game ID':gid,'Game start UTC':start.isoformat(),
          'First forecast UTC':now.isoformat(),'Home ID':h,'Away ID':a,'Home':g['Home'],'Away':g['Away'],
          'Venue':g['Venue'],'Baseline home margin':baseline,
          'Roster experimental home margin':experiment,'Roster eligible':bool(eligible),
          'Home retention %':adjustments[h]['retention'] if eligible else None,
          'Away retention %':adjustments[a]['retention'] if eligible else None,
          'Rating snapshot date':str(latest.iloc[0].get('As of UTC','')),
          'Source':'Saved daily ratings + ESPN fixture schedule; first pre-tip forecast',
          'Experimental coefficient':'0.5 rating points per 10% retention; cap 3/team; untrained'})
    return pd.DataFrame(new,columns=FIELDS)


def merge_immutable(existing,new):
    if existing.empty:return new.copy()
    if new.empty:return existing.copy()
    before=existing.copy()
    fresh=new[~new['Game ID'].astype(str).isin(set(before['Game ID'].astype(str)))]
    return pd.concat([before,fresh],ignore_index=True)


def evaluate_first_forecasts(archive,finals):
    if archive.empty or finals.empty:return pd.DataFrame()
    data=archive.copy()
    data['Game ID']=data['Game ID'].astype(str)
    data['First forecast UTC']=pd.to_datetime(data['First forecast UTC'],utc=True,errors='coerce')
    data['Game start UTC']=pd.to_datetime(data['Game start UTC'],utc=True,errors='coerce')
    data=data[data['First forecast UTC']<data['Game start UTC']].drop_duplicates('Game ID',keep='first')
    f=finals[finals['Status']=='Final'].copy()
    f['Game ID']=f['Game ID'].astype(str)
    joined=data.merge(f[['Game ID','Home score','Away score']].drop_duplicates('Game ID'),on='Game ID',how='inner')
    for c in ('Home score','Away score','Baseline home margin','Roster experimental home margin'):
        joined[c]=pd.to_numeric(joined[c],errors='coerce')
    joined=joined.dropna(subset=['Home score','Away score','Baseline home margin'])
    joined['Actual home margin']=joined['Home score']-joined['Away score']
    joined['Baseline absolute error']=(joined['Actual home margin']-joined['Baseline home margin']).abs()
    joined['Roster absolute error']=(joined['Actual home margin']-joined['Roster experimental home margin']).abs()
    return joined


def run(sport,now):
    root=ROOT/'predictions'/sport
    ratings_path=ROOT/'ratings'/sport/'latest.csv.gz'
    if not ratings_path.exists():raise RuntimeError('Missing saved daily ratings: run ratings workflow first')
    latest=read_gz(ratings_path)
    if latest.empty or not {'Team ID','Current power'}.issubset(latest.columns):raise RuntimeError('Invalid latest ratings')
    forecast_file=root/'first_forecasts.csv.gz'
    existing=read_gz(forecast_file,FIELDS)
    if not existing.empty and existing['Game ID'].duplicated().any():raise ValueError('Existing forecast archive contains duplicate game IDs; refuse to rewrite')
    schedule=fetch_events(sport,now)
    new=forecast_new_games(schedule,latest,load_saved_data(sport),now,sport,set(existing['Game ID'].astype(str)))
    all_forecasts=merge_immutable(existing,new)
    if not new.empty:save_gz(all_forecasts,forecast_file)
    # Scores live separately and can change (corrections), but original forecast rows never do.
    season_file=ROOT/'ratings'/sport/'season_2026-27.csv.gz'
    finals=read_gz(season_file)
    evaluation=evaluate_first_forecasts(all_forecasts,finals)
    if not evaluation.empty:save_gz(evaluation,root/'evaluated_games.csv.gz')
    n_eligible=int(new['Roster eligible'].sum()) if not new.empty else 0
    summary={'updated_utc':now.isoformat(),'division':sport,'new_forecasts':len(new),
        'new_roster_eligible':n_eligible,'archived_forecasts':len(all_forecasts),
        'evaluated_games':len(evaluation),'paired_model_games':int(evaluation['Roster absolute error'].notna().sum()) if not evaluation.empty else 0,
        'baseline_mae_all':float(evaluation['Baseline absolute error'].mean()) if not evaluation.empty else None,
        'baseline_mae_paired':float(evaluation.loc[evaluation['Roster absolute error'].notna(),'Baseline absolute error'].mean()) if not evaluation.empty and evaluation['Roster absolute error'].notna().any() else None,
        'roster_mae_paired':float(evaluation['Roster absolute error'].mean()) if not evaluation.empty and evaluation['Roster absolute error'].notna().any() else None,
        'notes':'First forecasts locked by Game ID; no overwrites. Paired error uses identical games. Rating and roster sources are experimental.'}
    root.mkdir(parents=True,exist_ok=True)
    (root/'status.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(f'{sport}: {len(new)} new (roster {n_eligible}), {len(all_forecasts)} archived, {len(evaluation)} evaluated')


def main():
    p=argparse.ArgumentParser();p.add_argument('--sport',choices=['both',*SPORTS],default='both')
    args=p.parse_args();errors=[]
    for sport in SPORTS if args.sport=='both' else [args.sport]:
        try:run(sport,utc_now())
        except Exception as exc:
            errors.append(f'{sport}: {exc}');print(f'FAILED {sport}: {exc}',flush=True)
    if errors:raise SystemExit('; '.join(errors))
if __name__=='__main__':main()

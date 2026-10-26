"""V97: prospective forecast journal. No app imports or model changes.

Official forecasts use the saved Current power snapshot and the same home +3
neutral 0 point convention as rating_engine/app. Models are archived only once
per game. Final results are stored separately, never backfilled as forecasts.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import os
import time
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
import pandas as pd

SPORTS = ('mens-college-basketball', 'womens-college-basketball')
HEADERS = {'User-Agent':'Mozilla/5.0 Courtside Prospective Research/1.0', 'Accept':'application/json'}
FIELDS = ['season','division','game_id','game_start_utc','game_date_et','home_id','away_id','home_team','away_team','neutral','model_id','forecast_created_utc','ratings_snapshot_utc','snapshot_file','snapshot_sha256','home_rating','away_rating','predicted_home_margin','forecast_type']
RESULT_FIELDS = ['season','division','game_id','game_start_utc','result_checked_utc','home_score','away_score','actual_home_margin','status']

def iso(dt): return dt.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def parse_dt(s):
    if not s: return None
    try:
        d = datetime.fromisoformat(str(s).strip().replace('Z','+00:00'))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except (ValueError,TypeError): return None

def score(c):
    x=c.get('score')
    if isinstance(x,dict):x=x.get('value',x.get('displayValue'))
    try: return int(float(x))
    except (TypeError,ValueError): return None

def event_data(e):
    comp=(e.get('competitions') or [{}])[0]
    teams=comp.get('competitors') or []
    home=next((x for x in teams if x.get('homeAway')=='home'),None)
    away=next((x for x in teams if x.get('homeAway')=='away'),None)
    start=parse_dt(e.get('date'))
    if not (home and away and start): return None
    h,a=home.get('team') or {},away.get('team') or {}
    hid,aid=str(h.get('id') or ''),str(a.get('id') or '')
    if not hid or not aid or hid==aid: return None
    typ=(e.get('status') or {}).get('type') or {}
    final=typ.get('completed') is True
    hs,aws=score(home),score(away)
    return dict(game_id=str(e.get('id') or ''),game_start_utc=iso(start),game_date_et=str(start.astimezone(ZoneInfo('America/New_York')).date()),home_id=hid,away_id=aid,home_team=h.get('displayName') or h.get('name') or hid,away_team=a.get('displayName') or a.get('name') or aid,neutral=bool(comp.get('neutralSite') is True),final=final,home_score=hs if final else None,away_score=aws if final else None)

def scoreboard(sport, day, session=None):
    ses=session or requests
    url=f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/scoreboard'
    response=ses.get(url,params={'dates':day.strftime('%Y%m%d'),'groups':'50','limit':500},headers=HEADERS,timeout=30)
    response.raise_for_status()
    payload=response.json()
    if not isinstance(payload.get('events'),list): raise RuntimeError(f'{sport} {day}: invalid ESPN response')
    if len(payload['events'])>=500: raise RuntimeError(f'{sport} {day}: possibly truncated scoreboard')
    out={}
    for e in payload['events']:
        x=event_data(e)
        if x and x['game_id']: out[x['game_id']]=x
    return out

def read_csv(path,fields):
    if not path.exists(): return []
    with path.open(newline='',encoding='utf-8') as f:
        r=csv.DictReader(f)
        if not set(fields).issubset(r.fieldnames or []): raise RuntimeError(f'Unexpected existing journal schema: {path}')
        return list(r)

def write_csv(path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    with tmp.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader();w.writerows(rows)
    os.replace(tmp,path)

def load_official(sport,root,now,max_age_hours=48):
    folder=root/'data'/'ratings'/sport
    snap=folder/'latest.csv.gz'; status=folder/'status.json'
    if not snap.exists() or not status.exists():return None,'missing saved ratings'
    meta=json.loads(status.read_text())
    asof=parse_dt(meta.get('updated_utc'))
    if asof is None:return None,'ratings lack dated updated_utc; cannot prove pregame freshness'
    age=(now-asof).total_seconds()/3600
    if age < 0 or age > max_age_hours:return None,f'ratings are not current ({age:.1f} hours old)'
    df=pd.read_csv(snap,dtype={'Team ID':str})
    if not {'Team ID','Current power'}.issubset(df.columns):return None,'saved ratings schema unavailable'
    df['Current power']=pd.to_numeric(df['Current power'],errors='coerce')
    df=df.dropna(subset=['Current power']).drop_duplicates('Team ID')
    return {'ratings':dict(zip(df['Team ID'].astype(str),df['Current power'].astype(float))), 'asof':asof, 'id':'official_saved_v97', 'file':str(snap.relative_to(root)), 'sha256':hashlib.sha256(snap.read_bytes()).hexdigest(), 'type':'official_saved_model'},None

def load_optional(sport,root,now,max_age_hours=48):
    # Only accept an explicit snapshot with a documented timestamp and model ID.
    file=root/'data'/'prospective'/'experimental_ratings'/sport/'latest.csv.gz'
    if not file.exists():return None,'not provided'
    df=pd.read_csv(file,dtype={'Team ID':str})
    required={'Team ID','Power','snapshot_utc','model_id'}
    if not required.issubset(df.columns):return None,'required experimental columns missing'
    if len(df)==0 or df['model_id'].nunique()!=1 or df['snapshot_utc'].nunique()!=1:return None,'experimental snapshot contains mixed sources'
    asof=parse_dt(df.iloc[0]['snapshot_utc'])
    if asof is None or not 0 <= (now-asof).total_seconds()/3600 <= max_age_hours:return None,'experimental rating timestamp invalid or stale'
    model=str(df.iloc[0]['model_id']).strip()
    if not model or model=='official_saved_v97' or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.' for c in model):return None,'invalid experimental model_id'
    df['Power']=pd.to_numeric(df['Power'],errors='coerce');df=df.dropna(subset=['Power']).drop_duplicates('Team ID')
    return {'ratings':dict(zip(df['Team ID'].astype(str),df['Power'].astype(float))), 'asof':asof, 'id':'experimental_'+model,'file':str(file.relative_to(root)),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'type':'optional_experimental'},None

def new_forecasts(games,models,existing,now,season,division,minimum_lead_minutes):
    keys={(x['division'],x['game_id'],x['model_id']) for x in existing}
    additions=[]
    for g in games.values():
        start=parse_dt(g['game_start_utc'])
        if g['final'] or start is None or start <= now+timedelta(minutes=minimum_lead_minutes): continue
        if start > now+timedelta(hours=42):continue
        for model in models:
            key=(division,g['game_id'],model['id'])
            if key in keys:continue
            if model['asof']>now or model['asof']>=start:continue
            ratings=model['ratings']
            if g['home_id'] not in ratings or g['away_id'] not in ratings:continue
            hm=float(ratings[g['home_id']]);am=float(ratings[g['away_id']])
            projected=hm-am+(0.0 if g['neutral'] else 3.0)
            if not math.isfinite(projected):continue
            rec={'season':season,'division':division,'game_id':g['game_id'],'game_start_utc':g['game_start_utc'],'game_date_et':g['game_date_et'],'home_id':g['home_id'],'away_id':g['away_id'],'home_team':g['home_team'],'away_team':g['away_team'],'neutral':str(g['neutral']).lower(),'model_id':model['id'],'forecast_created_utc':iso(now),'ratings_snapshot_utc':iso(model['asof']),'snapshot_file':model['file'],'snapshot_sha256':model['sha256'],'home_rating':round(hm,6),'away_rating':round(am,6),'predicted_home_margin':round(projected,6),'forecast_type':model['type']}
            additions.append(rec);keys.add(key)
    return additions

def settle(games,existing,results,now,season,division):
    # Results are one row per game. Never create a result unless a locked forecast exists.
    seen={(x['division'],x['game_id']) for x in results}
    eligible={(x['division'],x['game_id']) for x in existing}
    out=[]
    for g in games.values():
        key=(division,g['game_id'])
        if key in seen or key not in eligible or not g['final']:continue
        if g['home_score'] is None or g['away_score'] is None:continue
        if parse_dt(g['game_start_utc'])>=now:continue
        out.append({'season':season,'division':division,'game_id':g['game_id'],'game_start_utc':g['game_start_utc'],'result_checked_utc':iso(now),'home_score':g['home_score'],'away_score':g['away_score'],'actual_home_margin':g['home_score']-g['away_score'],'status':'Final'})
        seen.add(key)
    return out

def report(forecasts,results):
    scores={(r['division'],r['game_id']):r for r in results if r['status']=='Final'}
    groups={}
    for f in forecasts:
        # Crucial: a prediction made at or after scheduled tipoff is INVALID, irrespective of CSV contents.
        created=parse_dt(f['forecast_created_utc']);tip=parse_dt(f['game_start_utc']);asof=parse_dt(f['ratings_snapshot_utc'])
        if not created or not tip or not asof or not (asof<=created<tip):continue
        r=scores.get((f['division'],f['game_id']))
        if not r:continue
        p=float(f['predicted_home_margin']); actual=float(r['actual_home_margin'])
        k=(f['division'],f['model_id'])
        a=groups.setdefault(k,[]);a.append((p,actual,f['game_id']))
    out={}
    for (division,model),data in sorted(groups.items()):
        n=len(data)
        mae=sum(abs(a-b) for a,b,_ in data)/n
        # Pushes and predicted ties do not count as winner picks.
        valid=[(a,b) for a,b,_ in data if a!=0 and b!=0]
        win=sum((a>0)==(b>0) for a,b in valid)/len(valid) if valid else None
        # Brier score requires an actual forecast probability; do not invent one from margins.
        out[f'{division}/{model}']={'graded_games':n,'margin_mae':round(mae,4),'winner_accuracy_non_ties':round(win,4) if win is not None else None,'winner_sample':len(valid),'bias_actual_minus_prediction':round(sum(b-a for a,b,_ in data)/n,4),'brier_score':None,'brier_reason':'No saved pregame win probabilities'}
    return out

def run(root,now,season,minimum_lead_minutes=30,session=None):
    folder=root/'data'/'prospective'/season
    fpath=folder/'forecasts.csv';rpath=folder/'results.csv';summary=folder/'summary.json'
    forecasts=read_csv(fpath,FIELDS);results=read_csv(rpath,RESULT_FIELDS)
    info={}
    for sport in SPORTS:
        division='mens' if sport.startswith('mens') else 'womens'
        # ESPN date key is the event's ET date; fetch yesterday/today/tomorrow to cover settlements and schedule.
        today=now.astimezone(ZoneInfo('America/New_York')).date()
        fetched={};errors=[]
        for delta in (-2,-1,0,1,2):
            day=today+timedelta(days=delta)
            try:fetched.update(scoreboard(sport,day,session=session))
            except Exception as exc:errors.append(f'{day}: {exc}')
        if errors: # Fail closed: partial response must not appear as a complete run.
            raise RuntimeError(f'{division}: could not fetch all required scoreboard days: {errors}')
        official,err=load_official(sport,root,now)
        optional,opt_err=load_optional(sport,root,now)
        models=[m for m in (official,optional) if m is not None]
        added=new_forecasts(fetched,models,forecasts,now,season,division,minimum_lead_minutes)
        forecasts.extend(added)
        settled=settle(fetched,forecasts,results,now,season,division);results.extend(settled)
        info[division]={'games_seen':len(fetched),'forecasts_created':len(added),'results_added':len(settled),'official_ratings':err or 'available','experimental_ratings':opt_err or 'available'}
    if not fpath.exists() or any(v['forecasts_created'] for v in info.values()):write_csv(fpath,forecasts,FIELDS)
    if not rpath.exists() or any(v['results_added'] for v in info.values()):write_csv(rpath,results,RESULT_FIELDS)
    value={'version':97,'season':season,'as_of_utc':iso(now),'counts':{'immutable_forecasts':len(forecasts),'final_results':len(results)},'today':info,'evaluation':report(forecasts,results),'notes':['Official forecasts read saved current power snapshots; does not rebuild official rating generation.','Only the first qualifying pre-tip forecast per game/model is retained.','Outcome collection covers a rolling five-day window; rerun to catch delayed finals.','Experimental model results require separately timestamped input; no experimental model is fabricated.','No Brier score until genuine pregame win probabilities are stored.','Research-only: no live app or model change.']}
    summary.parent.mkdir(parents=True,exist_ok=True);summary.write_text(json.dumps(value,indent=2)+'\n')
    return value

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',default='.')
    parser.add_argument('--season',default='2026-27')
    parser.add_argument('--minimum-lead-minutes',type=int,default=30)
    args=parser.parse_args()
    now=datetime.now(timezone.utc)
    result=run(Path(args.root),now,args.season,args.minimum_lead_minutes)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()

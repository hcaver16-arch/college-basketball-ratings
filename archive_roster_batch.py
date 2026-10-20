"""Incremental archived source-data collector. Run in GitHub Actions, not Streamlit UI."""
import argparse
from pathlib import Path
import pandas as pd
import requests
from roster_tracking import read_roster
from player_stats_import import fetch_prior_stats

ROOT=Path(__file__).resolve().parent/"data"
ROOT.mkdir(exist_ok=True)

def read(kind,sport):
    p=ROOT/(sport+"_"+kind+".csv.gz")
    return pd.read_csv(p,dtype={"Team ID":str,"Player ID":str}) if p.exists() else pd.DataFrame()

def write(kind,sport,frame,key):
    if frame.empty:return
    p=ROOT/(sport+"_"+kind+".csv.gz")
    frame=frame.drop_duplicates(key,keep="last")
    frame.to_csv(p,index=False,compression={"method":"gzip","compresslevel":6,"mtime":0})

def directory(sport):
    url=f"https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/teams"
    response=requests.get(url,params={"limit":1000,"groups":"50"},timeout=30)
    response.raise_for_status()
    d=response.json()
    blocks=(d.get('sports') or [{}])[0].get('leagues') or []
    teams=[t for block in blocks for t in (block.get('teams') or [])]
    if not teams:teams=d.get('teams') or []
    entries=[]
    for item in teams:
        t=item.get('team',item)
        if t.get('id'):
            entries.append({'Team ID':str(t['id']),'Team':t.get('displayName') or t.get('name') or str(t['id'])})
    return pd.DataFrame(entries).drop_duplicates('Team ID')

def run(sport,limit,fetch_stats):
    schools=directory(sport)
    old=read('previous_rosters',sport)
    new=read('current_rosters',sport)
    stats=read('previous_stats',sport)
    status=read('collection_status',sport)
    # Do not treat empty/incomplete historical rosters as successful.
    completed=set(status.loc[status['state']=='collected','Team ID'].astype(str)) if not status.empty else set()
    selected=schools[~schools['Team ID'].isin(completed)].head(limit)
    print(sport, 'batch',len(selected),'of',len(schools),'directory schools')
    log=[];past=[];now=[];totals=[]
    for _,school in selected.iterrows():
        tid=str(school['Team ID']); name=str(school['Team'])
        try:
            a=read_roster(sport,tid,name,2026)
            b=read_roster(sport,tid,name,2027)
            if a.empty or b.empty: raise ValueError('one roster empty')
            past.append(a);now.append(b)
            if fetch_stats:
                s,diag,errs=fetch_prior_stats(sport,pd.DataFrame([school]),season=2026,max_games=45,max_workers=4)
                if not s.empty:totals.append(s)
                else: print('Statistics unavailable for',name)
            log.append({'Team ID':tid,'Team':name,'state':'collected','details':'roster snapshots fetched; season validity unverified'})
        except Exception as exc:
            log.append({'Team ID':tid,'Team':name,'state':'retry','details':type(exc).__name__+': '+str(exc)[:120]})
    def merge(existing,new_rows,key):
        if not new_rows:return existing
        added=pd.concat(new_rows,ignore_index=True)
        return pd.concat([existing,added],ignore_index=True).drop_duplicates(key,keep='last') if not existing.empty else added.drop_duplicates(key,keep='last')
    old=merge(old,past,['Team ID','Player ID'])
    new=merge(new,now,['Team ID','Player ID'])
    stats=merge(stats,totals,['Team ID','Player ID'])
    status=merge(status,[pd.DataFrame(log)],['Team ID']) if log else status
    for kind,frame,key in [('previous_rosters',old,['Team ID','Player ID']),('current_rosters',new,['Team ID','Player ID']),('previous_stats',stats,['Team ID','Player ID']),('collection_status',status,['Team ID'])]:
        write(kind,sport,frame,key)
    print('Completed:',sum(x['state']=='collected' for x in log),'needs retry:',sum(x['state']=='retry' for x in log))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--batch',type=int,default=12)
    p.add_argument('--sport',choices=['mens-college-basketball','womens-college-basketball','both'],default='both')
    a=p.parse_args()
    for sport in (['mens-college-basketball','womens-college-basketball'] if a.sport=='both' else [a.sport]):run(sport,a.batch,True)

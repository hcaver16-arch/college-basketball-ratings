"""Resumable roster/stat archive with evidence-based collection states.

Collection is provisional: ESPN may omit games, roster members, and box-score rows.
Existing good records are never removed by failed refreshes.
"""
import argparse
from pathlib import Path
import pandas as pd
import requests
from roster_tracking import read_roster
from player_stats_import import fetch_prior_stats

ROOT=Path(__file__).resolve().parent/'data'
ROOT.mkdir(exist_ok=True)

def read(kind,sport):
    p=ROOT/f'{sport}_{kind}.csv.gz'
    return pd.read_csv(p,dtype={'Team ID':str,'Player ID':str}) if p.exists() else pd.DataFrame()

def write(kind,sport,frame,key):
    if frame.empty:return
    p=ROOT/f'{sport}_{kind}.csv.gz'
    frame.drop_duplicates(key,keep='last').to_csv(p,index=False,compression={'method':'gzip','compresslevel':6,'mtime':0})

def directory(sport):
    url=f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/teams'
    r=requests.get(url,params={'limit':1000,'groups':'50'},timeout=30)
    r.raise_for_status()
    d=r.json()
    leagues=(d.get('sports') or [{}])[0].get('leagues') or []
    teams=[t for l in leagues for t in (l.get('teams') or [])] or d.get('teams') or []
    rows=[]
    for obj in teams:
        t=obj.get('team',obj)
        if t.get('id'):rows.append({'Team ID':str(t['id']),'Team':t.get('displayName') or t.get('name') or str(t['id'])})
    return pd.DataFrame(rows).drop_duplicates('Team ID')

def merge(existing,updates,keys):
    if not updates:return existing
    joined=pd.concat(([existing] if not existing.empty else [])+updates,ignore_index=True)
    return joined.drop_duplicates(keys,keep='last')

def run(sport,limit):
    schools=directory(sport)
    old,new,stats,status=[read(k,sport) for k in ('previous_rosters','current_rosters','previous_stats','collection_status')]
    finished=set(status.loc[status['state'].eq('collected'),'Team ID'].astype(str)) if not status.empty and 'state' in status else set()
    # Retry incomplete/retry schools, but mix in fresh schools so a broken feed cannot block progress.
    remaining=schools.loc[~schools['Team ID'].isin(finished)].copy()
    if not status.empty:
        state=dict(zip(status['Team ID'].astype(str),status['state'].astype(str)))
        remaining['_priority']=remaining['Team ID'].map(lambda x: 1 if state.get(str(x)) in ('retry','partial') else 0)
        # Fresh schools first; retries are addressed on subsequent batches without starvation of new schools.
        remaining=remaining.sort_values('_priority',kind='stable')
    selected=remaining.head(limit)
    log=[];past=[];now=[];totals=[]
    print(f'{sport}: processing {len(selected)} of {len(schools)} directory schools')
    for _,school in selected.iterrows():
        tid=str(school['Team ID']);name=str(school['Team'])
        row={'Team ID':tid,'Team':name,'state':'retry','details':'',
             'Completed games in feed':None,'Game box scores parsed':0,'Missing/invalid games':None,
             'Prior player totals rows':0}
        try:
            a=read_roster(sport,tid,name,2026);b=read_roster(sport,tid,name,2027)
            if a.empty or b.empty:raise ValueError('prior or current roster is empty')
            past.append(a);now.append(b)
            s,diag,errors=fetch_prior_stats(sport,pd.DataFrame([school]),season=2026,max_games=45,max_workers=4)
            d=diag.iloc[0].to_dict() if not diag.empty else {}
            for k in ('Completed games in feed','Game box scores parsed','Missing/invalid games'):
                row[k]=d.get(k)
            row['Prior player totals rows']=len(s)
            if not s.empty:totals.append(s)
            completed=pd.to_numeric(row['Completed games in feed'],errors='coerce')
            parsed=int(row['Game box scores parsed'] or 0)
            # No numeric guarantees about season completeness; this only verifies all fetched games parsed.
            if pd.notna(completed) and completed>0 and parsed==int(completed) and not s.empty:
                row['state']='collected'
                row['details']='All discovered completed box scores parsed; full season/roster unverified'
            else:
                row['state']='partial'
                row['details']=f'Incomplete box scores: {parsed}/{completed}; player rows {len(s)}. '+('; '.join(errors[:2]))[:160]
        except Exception as exc:
            row['details']=(type(exc).__name__+': '+str(exc))[:220]
        print(f"  {name}: {row['state']} games {row['Game box scores parsed']}/{row['Completed games in feed']} player rows {row['Prior player totals rows']}")
        log.append(row)
    old=merge(old,past,['Team ID','Player ID']);new=merge(new,now,['Team ID','Player ID'])
    stats=merge(stats,totals,['Team ID','Player ID']);status=merge(status,[pd.DataFrame(log)] if log else [],['Team ID'])
    for kind,frame,keys in [('previous_rosters',old,['Team ID','Player ID']),('current_rosters',new,['Team ID','Player ID']),('previous_stats',stats,['Team ID','Player ID']),('collection_status',status,['Team ID'])]:
        write(kind,sport,frame,keys)
    print('Collected',sum(x['state']=='collected' for x in log),'partial',sum(x['state']=='partial' for x in log),'retry',sum(x['state']=='retry' for x in log))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--batch',type=int,default=12)
    parser.add_argument('--sport',choices=['mens-college-basketball','womens-college-basketball','both'],default='both')
    args=parser.parse_args()
    for sport in (['mens-college-basketball','womens-college-basketball'] if args.sport=='both' else [args.sport]):run(sport,args.batch)

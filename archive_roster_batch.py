"""Resumable roster/stat archive with evidence-based collection states.

Collection is provisional: ESPN may omit games, roster members, and box-score rows.
Existing good records are never removed by failed refreshes.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests
from roster_tracking import read_roster
from player_stats_import import fetch_prior_stats
from roster_reconciliation import reconcile_prior_players

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

def select_batch(schools,status,limit,repair_only=False):
    """Reserve ~1/3 of each normal batch for old records missing coverage metadata.

    Other slots keep the archive growing. Oldest attempted repairs first so
    an intermittently failing endpoint cannot starve other legacy records.
    """
    if status.empty or 'Team ID' not in status:
        return schools.head(0) if repair_only else schools.head(limit).copy()
    st=status.copy()
    st['Team ID']=st['Team ID'].astype(str)
    st=st.drop_duplicates('Team ID',keep='last')
    indexed=schools.merge(st,how='left',on='Team ID',suffixes=('','_status'))
    discovered=pd.to_numeric(indexed.get('Completed games in feed',pd.Series(index=indexed.index,dtype=float)),errors='coerce')
    parsed=pd.to_numeric(indexed.get('Game box scores parsed',pd.Series(index=indexed.index,dtype=float)),errors='coerce')
    state=indexed.get('state',pd.Series(index=indexed.index,dtype=str)).fillna('new')
    missing_metadata=state.eq('collected') & (discovered.isna() | parsed.isna())
    needs_retry=state.isin(['partial','retry'])
    repair=indexed.loc[missing_metadata | needs_retry].copy()
    repair['_last']=pd.to_datetime(repair.get('Last audit attempt',pd.Series(index=repair.index,dtype=str)),errors='coerce',utc=True)
    repair=repair.sort_values('_last',kind='stable',na_position='first')
    fresh=indexed.loc[state.eq('new')].copy()
    if repair_only:
        return repair.head(limit)[['Team ID','Team']].copy()
    repair_slots=min(len(repair),max(1,limit//3)) if len(fresh) else limit
    selected=pd.concat([repair.head(repair_slots),fresh.head(limit-repair_slots)],ignore_index=True)
    if len(selected)<limit:
        selected=pd.concat([selected,repair.iloc[repair_slots:repair_slots+limit-len(selected)]],ignore_index=True)
    return selected[['Team ID','Team']].copy()

def run(sport,limit,repair_only=False):
    schools=directory(sport)
    old,new,stats,status=[read(k,sport) for k in ('previous_rosters','current_rosters','previous_stats','collection_status')]
    selected=select_batch(schools,status,limit,repair_only=repair_only)
    existing_status={str(r['Team ID']):r.to_dict() for _,r in status.iterrows()} if not status.empty else {}
    log=[];past=[];now=[];totals=[]
    print(f'{sport}: selected {len(selected)} of {len(schools)} directory schools (repair_only={repair_only})',flush=True)
    for _,school in selected.iterrows():
        tid=str(school['Team ID']);name=str(school['Team'])
        existing=existing_status.get(tid,{})
        row=dict(existing)
        row.update({'Team ID':tid,'Team':name,'Last audit attempt':datetime.now(timezone.utc).isoformat()})
        row.setdefault('Completed games in feed',None)
        row.setdefault('Game box scores parsed',None)
        row.setdefault('Missing/invalid games',None)
        row.setdefault('Prior player totals rows',0)
        was_collected=existing.get('state')=='collected'
        try:
            a=read_roster(sport,tid,name,2026);b=read_roster(sport,tid,name,2027)
            if a.empty or b.empty:raise ValueError('prior or current roster is empty')
            s,diag,errors=fetch_prior_stats(sport,pd.DataFrame([school]),season=2026,max_games=45,max_workers=4)
            d=diag.iloc[0].to_dict() if not diag.empty else {}
            completed=pd.to_numeric(d.get('Completed games in feed'),errors='coerce')
            parsed=pd.to_numeric(d.get('Game box scores parsed'),errors='coerce')
            missing=pd.to_numeric(d.get('Missing/invalid games'),errors='coerce')
            # Only replace archived stats on a valid, nonempty import. Preserve old rows
            # for a failed or empty response; never turn a missing count into zero.
            if pd.isna(completed) or completed<=0 or pd.isna(parsed):
                raise ValueError('No reliable completed-game and parsed-game counts in the response')
            row['Completed games in feed']=int(completed)
            row['Game box scores parsed']=int(parsed)
            row['Missing/invalid games']=int(missing) if pd.notna(missing) else max(0,int(completed)-int(parsed))
            if not s.empty:
                row['Prior player totals rows']=len(s)
                totals.append(s)
            past.append(a);now.append(b)
            if int(parsed)==int(completed) and not s.empty:
                row['state']='collected'
                row['details']='All discovered completed box scores parsed; full season/roster unverified'
            else:
                row['state']='partial'
                row['details']=f'Incomplete box scores: {int(parsed)}/{int(completed)}; player rows {len(s)}. '+('; '.join(errors[:2]))[:160]
        except Exception as exc:
            row['state']='partial' if was_collected else 'retry'
            row['details']=('Repair/collection failed; existing archived player records retained: '+type(exc).__name__+': '+str(exc))[:220]
        print(f"  {name}: {row['state']} games {row.get('Game box scores parsed')}/{row.get('Completed games in feed')} ({row['details'][:70]})",flush=True)
        log.append(row)
    old=merge(old,past,['Team ID','Player ID']);new=merge(new,now,['Team ID','Player ID'])
    stats=merge(stats,totals,['Team ID','Player ID']);status=merge(status,[pd.DataFrame(log)] if log else [],['Team ID'])
    prior_pool=reconcile_prior_players(old,stats)
    for kind,frame,keys in [('previous_player_pool',prior_pool,['Team ID','Player ID']),('previous_rosters',old,['Team ID','Player ID']),('current_rosters',new,['Team ID','Player ID']),('previous_stats',stats,['Team ID','Player ID']),('collection_status',status,['Team ID'])]:
        write(kind,sport,frame,keys)
    print('Collected',sum(x['state']=='collected' for x in log),'partial',sum(x['state']=='partial' for x in log),'retry',sum(x['state']=='retry' for x in log),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--batch',type=int,default=12)
    parser.add_argument('--sport',choices=['mens-college-basketball','womens-college-basketball','both'],default='both')
    parser.add_argument('--repair-only',action='store_true',help='Backfill old or partial records without using slots for new teams')
    args=parser.parse_args()
    for sport in (['mens-college-basketball','womens-college-basketball'] if args.sport=='both' else [args.sport]):run(sport,args.batch,repair_only=args.repair_only)

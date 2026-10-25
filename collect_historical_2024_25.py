"""Resumable 2024-25 D1-v-D1 paired box-score archive for exploratory backtests.

Collects a bounded consecutive set of dates per run, saving a durable cursor and
coverage ledger. Failed dates are retried on the next run, not silently skipped.
Season-specific ESPN conference membership must be verified before processing.
"""
from __future__ import annotations
import argparse
import datetime as dt
import io
import json
import os
import re
import time
from pathlib import Path
import pandas as pd
import requests

START = dt.date(2024, 11, 1)
END = dt.date(2025, 4, 15)  # inclusive; postseason may extend into early April
SPORTS = ('mens-college-basketball', 'womens-college-basketball')
ROOT = Path('data/historical_efficiency')
HEADERS = {'User-Agent': 'CourtsideAnalytics/1.0 personal research', 'Accept':'application/json'}
COLUMNS = ['game_id','date','home_id','away_id','home_points','away_points','possessions']


def fetch(session, url, params=None):
    for attempt in range(3):
        try:
            r=session.get(url,params=params,timeout=25)
            r.raise_for_status()
            obj=r.json()
            if not isinstance(obj,dict): raise ValueError('Response is not JSON object')
            return obj
        except (requests.RequestException,ValueError):
            if attempt<2:time.sleep(1+2*attempt)
    raise RuntimeError('Fetch failed: '+str(url))


def group_d1_ids(session, sport):
    """Resolve season 2024-25 D1 membership. Fail closed on incomplete groups."""
    base=f'https://sports.core.api.espn.com/v2/sports/basketball/leagues/{sport}/seasons/2025/types/2'
    def pages(url):
        items=[]; seen=set()
        while url:
            if url in seen: raise RuntimeError('Repeated pagination link')
            seen.add(url)
            doc=fetch(session,url)
            if not isinstance(doc.get('items'),list): raise RuntimeError('Malformed ESPN group response')
            items.extend(doc['items'])
            page=doc.get('page') or {}
            url=page.get('next')
        return items
    groups=pages(base+'/groups/50/children?limit=200')
    if not 25 <= len(groups) <= 50:raise RuntimeError(f'Unexpected D1 conference count {len(groups)}')
    ids=set()
    for item in groups:
        ref=item.get('$ref','')
        if not ref:raise RuntimeError('Conference reference missing')
        group=fetch(session,ref)
        gid=group.get('id')
        if not gid:raise RuntimeError('Conference id missing')
        for entry in pages(base+f'/groups/{gid}/teams?limit=500'):
            ref=str(entry.get('$ref','')).split('?')[0].rstrip('/')
            if not ref:raise RuntimeError('Team reference missing')
            tid=ref.rsplit('/',1)[-1]
            if not tid.isdigit():raise RuntimeError('Invalid ESPN team ID: '+tid)
            ids.add(tid)
    if not 300 <= len(ids) <= 400:raise RuntimeError(f'Unexpected verified D1 team count {len(ids)}')
    return ids


def possessions_from_summary(doc, home_id, away_id):
    """Extract paired final-game points and averaged possession estimate."""
    competitions=(doc.get('header') or {}).get('competitions') or []
    if not competitions:return None
    comp=competitions[0]
    if not (comp.get('status') or {}).get('type',{}).get('completed'):return None
    score={str(x.get('team',{}).get('id','')):x.get('score') for x in comp.get('competitors',[])}
    estimated={}
    for team in (doc.get('boxscore') or {}).get('teams',[]):
        tid=str(team.get('team',{}).get('id',''))
        values={str(s.get('name')):s.get('displayValue',s.get('value')) for s in team.get('statistics',[])}
        def attempts(stem):
            val=values.get(stem+'Made-'+stem+'Attempted')
            if val is not None:
                parts=str(val).replace(' ','').split('-')
                if len(parts)==2:return float(parts[1])
            item=values.get(stem+'Attempted')
            return float(item) if item is not None else None
        try:
            fga=attempts('fieldGoals');fta=attempts('freeThrows')
            orb=float(values['offensiveRebounds']);tov=float(values['turnovers'])
            if fga is None or fta is None:continue
            if min(fga,fta,orb,tov)<0:continue
            estimated[tid]=fga+.44*fta-orb+tov
        except (TypeError,ValueError,KeyError):continue
    if home_id not in estimated or away_id not in estimated:return None
    try:
        hp=float(score[home_id]);ap=float(score[away_id])
        poss=(estimated[home_id]+estimated[away_id])/2
        if not (35<=poss<=120 and 0<=hp<=200 and 0<=ap<=200):return None
        return hp,ap,round(poss,3)
    except (ValueError,TypeError,KeyError):return None


def parse_day(session,sport,date,d1):
    board=fetch(session,f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/scoreboard',
                {'dates':date.strftime('%Y%m%d'),'groups':'50','limit':500})
    events=board.get('events')
    if not isinstance(events,list) or len(events)>=500:raise RuntimeError('Missing/truncated scoreboard events')
    rows=[]; diag={'events':len(events),'completed':0,'d1_finals':0,'usable':0,'missing_box':0}
    for event in events:
        comp=(event.get('competitions') or [None])[0]
        if not comp or not (comp.get('status') or {}).get('type',{}).get('completed'):continue
        diag['completed']+=1
        competitors=comp.get('competitors') or []
        home=next((x for x in competitors if x.get('homeAway')=='home'),None)
        away=next((x for x in competitors if x.get('homeAway')=='away'),None)
        if not home or not away:continue
        h=str(home.get('team',{}).get('id',''));a=str(away.get('team',{}).get('id',''))
        if h not in d1 or a not in d1 or h==a:continue
        diag['d1_finals']+=1
        gid=str(event.get('id',''))
        if not gid or not gid.isdigit():continue
        try:
            summary=fetch(session,f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/summary',{'event':gid})
        except RuntimeError:
            diag['missing_box']+=1;continue
        paired=possessions_from_summary(summary,h,a)
        if paired is None:diag['missing_box']+=1;continue
        rows.append({'game_id':gid,'date':str(date),'home_id':h,'away_id':a,
                     'home_points':paired[0],'away_points':paired[1],'possessions':paired[2]})
        diag['usable']+=1
    return rows,diag


def collect(sport, batch_days, root=ROOT, session=None, membership=None):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    stem='2024-25_'+('mens' if sport==SPORTS[0] else 'womens')
    data_path=root/(stem+'_paired_games.csv.gz')
    state_path=root/(stem+'_collection_status.json')
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    last=state.get('last_completed_date')
    start=dt.date.fromisoformat(last)+dt.timedelta(days=1) if last else START
    if start>END:
        print(f'{sport}: collection already complete through {END}')
        return
    owns=session is None
    session=session or requests.Session()
    if owns: session.headers.update(HEADERS)
    try:
        d1=membership if membership is not None else group_d1_ids(session,sport)
        if len(d1)<300:raise RuntimeError('D1 membership too small')
    except Exception as exc:
        print(f'{sport}: membership verification failed; cannot collect safely: {exc}')
        # Fail the workflow to distinguish source failure from a successful zero-game day.
        raise
    prior=pd.read_csv(data_path,dtype={'game_id':str,'home_id':str,'away_id':str}) if data_path.exists() else pd.DataFrame(columns=COLUMNS)
    days=state.get('days',{})
    processed=0
    for n in range(batch_days):
        day=start+dt.timedelta(days=n)
        if day>END:break
        try:
            rows, diag=parse_day(session,sport,day,d1)
            # Atomic, idempotent write: old files remain intact on failure.
            new=pd.DataFrame(rows,columns=COLUMNS)
            combined=pd.concat([prior,new],ignore_index=True) if not prior.empty and not new.empty else (new.copy() if prior.empty else prior.copy())
            if combined.game_id.duplicated().any():
                duplicates=combined.loc[combined.game_id.duplicated(keep=False)]
                for _,grp in duplicates.groupby('game_id'):
                    if grp[COLUMNS].astype(str).drop_duplicates().shape[0]>1:
                        raise RuntimeError('Conflicting values for game ID '+str(grp.game_id.iloc[0]))
            combined=combined.drop_duplicates('game_id').sort_values(['date','game_id'])
            temp=data_path.with_name(data_path.name+'.tmp')
            combined.to_csv(temp,index=False,compression='gzip')
            os.replace(temp,data_path)
            prior=combined
            days[str(day)]=diag
            state={'sport':sport,'season':'2024-25','first_date':str(START),'last_date':str(END),
                   'last_completed_date':str(day),'days':days,'games_archived':int(len(prior)),
                   'notes':'Days marked complete if scoreboard fetched; individual missing box scores counted, not silently discarded. ESPN unofficial API.'}
            s_tmp=state_path.with_name(state_path.name+'.tmp')
            s_tmp.write_text(json.dumps(state,indent=2)+'\n');os.replace(s_tmp,state_path)
            processed+=1
            print(f'{sport} {day}: {diag}; total verified paired games={len(prior)}',flush=True)
        except Exception as exc:
            print(f'{sport}: stopping at {day}; will retry this date: {exc}',flush=True)
            raise
    print(f'{sport}: processed {processed} days; next date '+str(start+dt.timedelta(days=processed)))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--sport',choices=['both',*SPORTS],default='both')
    p.add_argument('--batch-days',type=int,default=3)
    p.add_argument('--root',default=str(ROOT))
    args=p.parse_args()
    if not 1<=args.batch_days<=10:p.error('--batch-days must be between 1 and 10')
    for sport in SPORTS if args.sport=='both' else [args.sport]:
        collect(sport,args.batch_days,root=Path(args.root))
if __name__=='__main__':main()

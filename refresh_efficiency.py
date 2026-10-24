"""Build independent experimental ratings from completed ESPN team box scores.

Daily incremental update. Does not modify official ratings, predictions, or app.py.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import time
from pathlib import Path
import pandas as pd
import requests
from adjusted_efficiency import fit_adjusted_efficiency

ROOT = Path('data/efficiency')
SEASON_START = dt.date(2026, 11, 1)
SPORTS = ('mens-college-basketball', 'womens-college-basketball')
HEADERS = {'User-Agent':'CourtsideAnalytics/1.0 (personal research)', 'Accept':'application/json'}


def get_json(session, url, params=None):
    for attempt in range(3):
        try:
            r = session.get(url, params=params, timeout=24)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            if attempt == 2:
                return None
            time.sleep(1 + attempt * 2)
    return None


def paired_boxscore(doc, home_id, away_id):
    """Return verified paired final scores and shared possession estimate."""
    if not isinstance(doc, dict):
        return None
    comps = doc.get('header',{}).get('competitions') or []
    if not comps or not (comps[0].get('status',{}).get('type',{}).get('completed')):
        return None
    scores = {str(c.get('team',{}).get('id')): c.get('score') for c in comps[0].get('competitors',[])}
    stats = {}
    for t in doc.get('boxscore',{}).get('teams',[]):
        tid = str(t.get('team',{}).get('id',''))
        values = {str(s.get('name')):s.get('displayValue',s.get('value')) for s in t.get('statistics',[])}
        def pair(stem):
            value = values.get(stem+'Made-'+stem+'Attempted')
            if value is not None and '-' in str(value):
                return [float(v) for v in str(value).split('-',1)]
            a,b=values.get(stem+'Made'),values.get(stem+'Attempted')
            return [float(a),float(b)] if a is not None and b is not None else None
        try:
            fg, ft = pair('fieldGoals'), pair('freeThrows')
            if fg is None or ft is None:
                continue
            oreb = float(values['offensiveRebounds']); tov = float(values['turnovers'])
            stats[tid] = fg[1] + .44*ft[1] - oreb + tov
        except (ValueError, KeyError, TypeError):
            continue
    h,a = str(home_id),str(away_id)
    try:
        if h not in stats or a not in stats: return None
        hp,ap=float(scores[h]),float(scores[a])
        possessions = (stats[h]+stats[a])/2
        if not 35 <= possessions <= 120: return None
        return hp,ap,possessions
    except (KeyError,TypeError,ValueError):
        return None


def verified_membership(session, sport):
    """Resolve current-season D1 school IDs from ESPN's conference group hierarchy.

    Fail closed if any conference membership request is incomplete.
    """
    base = (f'https://sports.core.api.espn.com/v2/sports/basketball/leagues/{sport}'
            '/seasons/2027/types/2')
    def pages(url):
        found=[]
        while url:
            data=get_json(session,url)
            if data is None or 'items' not in data:
                raise RuntimeError('Incomplete conference membership pages')
            found.extend(data['items'])
            url=(data.get('page') or {}).get('next')
        return found
    children=pages(base+'/groups/50/children?limit=200')
    if len(children) < 25:
        raise RuntimeError('Too few D1 conferences identified')
    ids=set()
    for ref in children:
        address=ref.get('$ref')
        group=get_json(session,address) if address else None
        if not group or group.get('id') is None:
            raise RuntimeError('Unresolved conference group')
        for record in pages(base+'/groups/'+str(group['id'])+'/teams?limit=500'):
            endpoint=str(record.get('$ref','')).split('?')[0].rstrip('/')
            if endpoint:
                ids.add(endpoint.rsplit('/',1)[-1])
    return ids


def gather(sport, until, *, max_days=14):
    ROOT.mkdir(parents=True, exist_ok=True)
    path = ROOT / f'{sport}_paired_games.csv.gz'
    existing = pd.read_csv(path, dtype={'game_id':str,'home_id':str,'away_id':str}) if path.exists() else pd.DataFrame()
    known = set(existing.game_id.astype(str)) if 'game_id' in existing else set()
    session = requests.Session(); session.headers.update(HEADERS)
    dates = [until-dt.timedelta(days=i) for i in range(max_days-1,-1,-1) if until-dt.timedelta(days=i)>=SEASON_START]
    additions = []; incomplete_days = []
    for date in dates:
        data = get_json(session, f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/scoreboard',
                        {'dates':date.strftime('%Y%m%d'),'groups':'50','limit':500})
        if data is None or not isinstance(data.get('events'),list) or len(data['events']) >= 500:
            incomplete_days.append(str(date)); continue
        for event in data['events']:
            gid=str(event.get('id',''))
            if not gid or gid in known: continue
            comps=event.get('competitions') or []
            if not comps: continue
            comp=comps[0]
            if not comp.get('status',{}).get('type',{}).get('completed'): continue
            opponents=comp.get('competitors') or []
            home=next((c for c in opponents if c.get('homeAway')=='home'),None)
            away=next((c for c in opponents if c.get('homeAway')=='away'),None)
            if not home or not away:continue
            hid=str(home.get('team',{}).get('id','')); aid=str(away.get('team',{}).get('id',''))
            # ESPN group=50 is a discovery filter, not proof each opponent is D1.
            # Require D1 group/membership validation before a production-wide rollout.
            if not hid or not aid:continue
            doc=get_json(session,f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/summary',{'event':gid})
            vals=paired_boxscore(doc,hid,aid)
            if vals is None: continue
            additions.append({'game_id':gid,'date':str(date),'home_id':hid,'away_id':aid,
                              'home_points':vals[0],'away_points':vals[1],'possessions':vals[2]})
            known.add(gid)
    combined=pd.concat([existing,pd.DataFrame(additions)],ignore_index=True) if not existing.empty else pd.DataFrame(additions)
    if not combined.empty:
        combined=combined.drop_duplicates('game_id').sort_values(['date','game_id'])
        combined.to_csv(path,index=False,compression='gzip')
    print(f'{sport}: {len(additions)} new paired finals; {len(combined)} cumulative; incomplete days: {incomplete_days}')
    if incomplete_days:
        print('Partial fetch: not publishing a new adjusted snapshot.')
        return
    if combined.empty: return
    # To protect scientific validity, do not include non-D1 games in fitting.
    # This snapshot remains inactive until a verified D1 membership file is provided.
    try:
        members = verified_membership(session, sport)
    except Exception as ex:
        print(f'Could not verify D1 membership: {ex}; adjusted ratings withheld.')
        return
    if len(members) < 300:
        print(f'Only {len(members)} D1 teams verified; adjusted ratings withheld.')
        return
    eligible=combined[combined.home_id.astype(str).isin(members)&combined.away_id.astype(str).isin(members)]
    fitted=fit_adjusted_efficiency(eligible)
    if fitted.empty:return
    fitted['Snapshot UTC']=dt.datetime.now(dt.timezone.utc).isoformat()
    fitted['Season']='2026-27'
    fitted['Source']='ESPN paired final box scores; independently validated D1 members'
    fitted.to_csv(ROOT/f'{sport}_adjusted_latest.csv', index=False)
    print(f'{sport}: published {len(fitted)} team rows; {fitted.adj_o.notna().sum()} with sufficient game sample')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--days',type=int,default=14)
    parser.add_argument('--sport',choices=['both',*SPORTS],default='both')
    args=parser.parse_args()
    until=dt.datetime.now(dt.timezone.utc).date()
    for sport in SPORTS if args.sport=='both' else [args.sport]:
        gather(sport,until,max_days=max(1,min(args.days,220)))
if __name__=='__main__':main()

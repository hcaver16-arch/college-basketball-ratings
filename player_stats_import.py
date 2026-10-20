"""Auditable ESPN box-score aggregation for previous-season individual totals.

Unofficial API, verified by the hosted dashboard at run time. Never extrapolates
missing box scores or treats a partial subset as full-season production.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import requests
import pandas as pd

FIELDS = ['Team ID','Player ID','Minutes','Points','Rebounds','Assists','Source']
HEADERS = {'User-Agent':'Mozilla/5.0 (compatible; college-basketball-research/1.0)', 'Accept':'application/json'}
STAT_ALIASES = {'Minutes':['MIN','minutes'], 'Points':['PTS','points'], 'Rebounds':['REB','rebounds'], 'Assists':['AST','assists']}

def parse_minutes(v):
    if v is None or str(v).strip() in ('','--','DNP'): return None
    s=str(v).strip()
    try:
        if ':' in s:
            m,sec=s.split(':',1);return float(m)+float(sec)/60
        return float(s)
    except (ValueError,TypeError): return None

def numeric(v):
    try:
        n=float(str(v).replace(',',''))
        return n if n>=0 else None
    except (TypeError,ValueError): return None

def parse_boxscore(data, team_id, game_id):
    """Return ESPN athlete rows for ONE requested team or [] if shape invalid."""
    players=((data.get('boxscore') or {}).get('players') or [])
    extracted=[]
    for group in players:
        tid=str((group.get('team') or {}).get('id') or '')
        if tid!=str(team_id):continue
        for block in group.get('statistics') or []:
            labels=[str(x).strip().upper() for x in (block.get('labels') or block.get('names') or [])]
            slots={k:next((i for i,n in enumerate(labels) if n in [a.upper() for a in aliases]),None) for k,aliases in STAT_ALIASES.items()}
            if any(v is None for v in slots.values()):continue
            for item in block.get('athletes') or []:
                athlete=item.get('athlete') or {}
                pid=str(athlete.get('id') or '')
                values=item.get('stats') or []
                if not pid or not values or item.get('didNotPlay') or item.get('inactive'):continue
                if max(slots.values())>=len(values):continue
                nums={k:(parse_minutes(values[idx]) if k=='Minutes' else numeric(values[idx])) for k,idx in slots.items()}
                if any(v is None for v in nums.values()):continue
                extracted.append({'Team ID':str(team_id),'Player ID':pid,**nums,'Game ID':str(game_id)})
    return extracted

def games_from_schedule(data):
    output=set()
    for item in data.get('events') or []:
        event_id=str(item.get('id') or '')
        status=(item.get('status') or {}).get('type') or {}
        if event_id and status.get('completed'): output.add(event_id)
    return sorted(output)

def fetch_prior_stats(sport, teams, season=2026, max_games=45, max_workers=4, session=None):
    """Return (stats, diagnostics, warnings). Per team audit includes scheduled/completed/parsed counts."""
    s=session or requests
    stats=[]; audits=[]; errors=[]
    for _,team in teams.iterrows():
        tid=str(team['Team ID']);label=str(team['Team'])
        schedule_url=f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/teams/{tid}/schedule'
        try:
            response=s.get(schedule_url,params={'season':season},headers=HEADERS,timeout=25)
            response.raise_for_status()
            gids=games_from_schedule(response.json())
        except Exception as e:
            errors.append(f'{label}: schedule unavailable ({str(e)[:125]})')
            audits.append({'Team':label,'Completed games in feed':None,'Game box scores parsed':0,'Missing/invalid games':None,'Coverage':'Unavailable'})
            continue
        if len(gids)>max_games:
            errors.append(f'{label}: {len(gids)} games exceed safety limit {max_games}; statistics withheld.')
            audits.append({'Team':label,'Completed games in feed':len(gids),'Game box scores parsed':0,'Missing/invalid games':len(gids),'Coverage':'Unverified — over limit'})
            continue
        parsed=0; rows=[]
        def load(game_id):
            url=f'https://site.web.api.espn.com/apis/site/v2/sports/basketball/{sport}/summary'
            r=s.get(url,params={'event':game_id},headers=HEADERS,timeout=25)
            r.raise_for_status()
            return parse_boxscore(r.json(),tid,game_id)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures={pool.submit(load,g):g for g in gids}
            for future in as_completed(futures):
                try:
                    game_rows=future.result()
                    if game_rows:
                        parsed+=1;rows.extend(game_rows)
                except Exception as e:
                    errors.append(f'{label} game {futures[future]}: {str(e)[:100]}')
        # Identical athlete/game rows cannot count twice.
        df=pd.DataFrame(rows)
        if not df.empty:
            df=df.drop_duplicates(['Team ID','Player ID','Game ID'])
            for pid,group in df.groupby('Player ID'):
                row={'Team ID':tid,'Player ID':str(pid),'Source':f'ESPN boxscores / {sport} / season {season} / {parsed} of {len(gids)} games'}
                for stat in ('Minutes','Points','Rebounds','Assists'):row[stat]=round(float(group[stat].sum()),2)
                stats.append(row)
        missing=len(gids)-parsed
        audits.append({'Team':label,'Completed games in feed':len(gids),'Game box scores parsed':parsed,'Missing/invalid games':missing,
                       'Coverage':('All fetched box scores parsed — season completeness unverified' if gids and missing==0 else 'Incomplete; do not treat totals as full season')})
    result=pd.DataFrame(stats,columns=FIELDS)
    return result,pd.DataFrame(audits),errors

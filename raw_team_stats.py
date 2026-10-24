"""ESPN final-game boxscore aggregation for display only; no model effects.

Limited to loaded completed games, with per-game caching and transparent coverage.
ESPN's public endpoint is unofficial and may change.
"""
from __future__ import annotations
import math
import re
import pandas as pd
import requests
import streamlit as st

STAT_NAMES = {
    'fieldGoalsMade-fieldGoalsAttempted':'fg', 'threePointFieldGoalsMade-threePointFieldGoalsAttempted':'three',
    'freeThrowsMade-freeThrowsAttempted':'ft', 'offensiveRebounds':'oreb',
    'defensiveRebounds':'dreb', 'totalRebounds':'reb', 'assists':'ast',
    'turnovers':'tov', 'steals':'stl', 'blocks':'blk',
}

def _float(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None

def _pair(v):
    m=re.match(r'^\s*(\d+)\s*[-/]\s*(\d+)\s*$',str(v))
    return (int(m.group(1)),int(m.group(2))) if m else None

@st.cache_data(ttl=21600,show_spinner=False)
def _boxscore(game_id,league):
    try:
        if not re.fullmatch(r'\d{6,12}',str(game_id)):
            return {}
        sport='womens-college-basketball' if str(league).lower().startswith('women') else 'mens-college-basketball'
        url=f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/summary'
        res=requests.get(url,params={'event':str(game_id)},timeout=9)
        res.raise_for_status()
        doc=res.json()
        out={}
        for item in doc.get('boxscore',{}).get('teams',[]):
            tid=str(item.get('team',{}).get('id',''))
            if not tid:continue
            stats={}
            for stat in item.get('statistics',[]):
                name=str(stat.get('name') or stat.get('abbreviation') or '')
                value=stat.get('displayValue',stat.get('value'))
                key=STAT_NAMES.get(name)
                if key:
                    stats[key]=_pair(value) if key in ('fg','three','ft') else _float(value)
                elif name in ('fieldGoalsMade','fieldGoalsAttempted','threePointFieldGoalsMade','threePointFieldGoalsAttempted','freeThrowsMade','freeThrowsAttempted'):
                    stats[name]=_float(value)
            for key,stem in (('fg','fieldGoals'),('three','threePointFieldGoals'),('ft','freeThrows')):
                if key not in stats:
                    a,b=stats.get(stem+'Made'),stats.get(stem+'Attempted')
                    if a is not None and b is not None:stats[key]=(a,b)
            out[tid]=stats
        return out
    except (requests.RequestException,ValueError,TypeError,KeyError):return {}

def team_raw_stats(games,tid,league,*,before=None,max_games=45):
    if not isinstance(games,pd.DataFrame) or games.empty:return None
    needed={'Game ID','Status','Home ID','Away ID'}
    if not needed.issubset(games.columns):return None
    g=games[(games['Home ID'].astype(str)==str(tid))|(games['Away ID'].astype(str)==str(tid))].copy()
    g=g[g['Status'].astype(str).str.contains('final',case=False,na=False)]
    if 'Date' in g:
        g['_date']=pd.to_datetime(g['Date'],errors='coerce',utc=True)
        if before is not None:
            dt=pd.to_datetime(before,errors='coerce',utc=True)
            if pd.notna(dt):g=g[g['_date']<dt]
        g=g.sort_values('_date')
    ids=g['Game ID'].dropna().astype(str).drop_duplicates().tail(max_games).tolist()
    totals={k:0.0 for k in ('fgm','fga','tpm','tpa','ftm','fta','reb','oreb','dreb','ast','tov','stl','blk','points')}
    counts={k:0 for k in totals}
    valid=0
    for gid in ids:
        stat=_boxscore(gid,league).get(str(tid),{})
        if not stat:continue
        valid+=1
        for key,first in (('fg','fgm'),('three','tpm'),('ft','ftm')):
            pair=stat.get(key)
            if pair is not None:
                second={'fg':'fga','three':'tpa','ft':'fta'}[key]
                totals[first]+=pair[0];totals[second]+=pair[1];counts[first]+=1;counts[second]+=1
        for key in ('reb','oreb','dreb','ast','tov','stl','blk'):
            value=stat.get(key)
            if value is not None:totals[key]+=value;counts[key]+=1
    if not valid:return None
    values={'validated':True,'boxscore_games':valid,'eligible_final_games':len(ids)}
    def rate(n,d,mult=1):return mult*totals[n]/totals[d] if counts[n]==valid and counts[d]==valid and totals[d]>0 else None
    for key,source in (('reb_pg','reb'),('ast_pg','ast'),('tov_pg','tov'),('stl_pg','stl'),('blk_pg','blk')):
        if counts[source]==valid:values[key]=totals[source]/valid
    if counts['fga']==valid and counts['fgm']==valid:
        values['fg_pct']=rate('fgm','fga',100)
    if counts['tpa']==valid and counts['tpm']==valid:values['three_pct']=rate('tpm','tpa',100)
    if counts['fta']==valid and counts['ftm']==valid:values['ft_pct']=rate('ftm','fta',100)
    if counts['fga']==valid and counts['fgm']==valid and counts['tpm']==valid and counts['fga']>0:
        values['efg_pct']=100*(totals['fgm']+.5*totals['tpm'])/totals['fga']
    if counts['fga']==valid and counts['tpa']==valid and counts['fgm']==valid and counts['tpm']==valid and totals['fga']>totals['tpa']:
        values['two_pct']=100*(totals['fgm']-totals['tpm'])/(totals['fga']-totals['tpa'])
    if counts['ast']==valid and counts['tov']==valid and totals['tov']>0:values['ast_tov']=totals['ast']/totals['tov']
    if counts['ast']==valid and counts['fgm']==valid and totals['fgm']>0:values['ast_pct']=100*totals['ast']/totals['fgm']
    if counts['fta']==valid and counts['fga']==valid and totals['fga']>0:values['ftr']=totals['fta']/totals['fga']
    if counts['tov']==valid and counts['fga']==valid and counts['fta']==valid:
        pos=totals['fga']+.44*totals['fta']+totals['tov']-(totals['oreb'] if counts['oreb']==valid else 0)
        if counts['oreb']==valid and pos>0:
            values['possessions']=pos/valid
            values['tov_pct']=100*totals['tov']/pos
    return values

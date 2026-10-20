"""Prospective, untrained roster-sensitivity experiment.
Never uses postgame results to construct forecasts; missing roster evidence is not zero.
"""
from __future__ import annotations
import pandas as pd
from datetime import datetime, timezone

DEFAULT_SLOPE = 0.5  # assumed points / 10 percentage points returning minutes


def evidence_adjustments(previous, current, player_totals, team_ids, slope=DEFAULT_SLOPE, reference=50):
    from saved_roster_data import team_saved_analysis
    result = {}
    for tid in sorted({str(x) for x in team_ids}):
        saved = team_saved_analysis(tid, previous, current, player_totals)
        if not saved or saved['returning'].empty: continue
        row = saved['returning'].iloc[0]
        retention = pd.to_numeric(row.get('Returning minutes % (known only)'),errors='coerce')
        n = pd.to_numeric(row.get('Prior roster entries'),errors='coerce')
        matched = pd.to_numeric(row.get('Prior roster players with stats'),errors='coerce')
        if pd.isna(retention) or pd.isna(n) or pd.isna(matched) or n < 8 or matched/n < .9: continue
        # This is an assumption, not a fitted player-impact coefficient.
        delta = max(-3.0,min(3.0, (float(retention)-reference)/10.0*slope))
        result[tid] = {'adjustment':round(delta,3),'retention':round(float(retention),2),'matched':int(matched),'prior_count':int(n)}
    return result


def make_forecasts(schedule, power_lookup, adjustments, snapshot_date, division, home_advantage=3.0):
    rows=[]
    for _, game in schedule.iterrows():
        if str(game.get('Status')) != 'Scheduled':continue
        h,a=str(game.get('Home ID','')),str(game.get('Away ID',''))
        if h not in adjustments or a not in adjustments:continue
        try:
            hp=float(power_lookup[h]); ap=float(power_lookup[a])
        except (KeyError, ValueError, TypeError):continue
        if pd.isna(hp) or pd.isna(ap):continue
        loc=str(game.get('Venue',''))
        adv=0 if loc.lower()=='neutral' else home_advantage
        baseline=hp-ap+adv
        delta=adjustments[h]['adjustment']-adjustments[a]['adjustment']
        rows.append({'Forecast date UTC':snapshot_date,'Division':division,'Game ID':str(game.get('Game ID','')),
            'Game date':str(game.get('Date','')),'Home ID':h,'Away ID':a,'Home':game.get('Home'),'Away':game.get('Away'),
            'Baseline home margin':round(baseline,2),'Roster experimental home margin':round(baseline+delta,2),
            'Home retention %':adjustments[h]['retention'],'Away retention %':adjustments[a]['retention'],
            'Model status':'Untrained assumption; retrospective team roster source may change',
            'Assumed slope':DEFAULT_SLOPE})
    return pd.DataFrame(rows)


def evaluate_forecasts(forecasts, completed_games):
    """Requires forecasts dated strictly before the game date. Match by unique ESPN game ID."""
    need={'Forecast date UTC','Game date','Game ID','Baseline home margin','Roster experimental home margin'}
    if not need.issubset(forecasts.columns):raise ValueError('CSV is missing required forecast columns')
    finals=completed_games[completed_games['Status']=='Final'].copy()
    finals['Game ID']=finals['Game ID'].astype(str)
    finals=finals.drop_duplicates('Game ID')
    fs=forecasts.copy()
    fs['Game ID']=fs['Game ID'].astype(str)
    fs['Forecast date UTC']=pd.to_datetime(fs['Forecast date UTC'],utc=True,errors='coerce')
    fs['Game date']=pd.to_datetime(fs['Game date'],utc=True,errors='coerce')
    fs=fs[fs['Forecast date UTC']<fs['Game date']]
    fs=fs.sort_values('Forecast date UTC').drop_duplicates('Game ID',keep='last')
    out=fs.merge(finals[['Game ID','Home score','Away score']],on='Game ID',how='inner')
    for col in ['Home score','Away score','Baseline home margin','Roster experimental home margin']:
        out[col]=pd.to_numeric(out[col],errors='coerce')
    out=out.dropna(subset=['Home score','Away score','Baseline home margin','Roster experimental home margin'])
    out['Actual home margin']=out['Home score']-out['Away score']
    out['Baseline absolute error']=(out['Actual home margin']-out['Baseline home margin']).abs()
    out['Experimental absolute error']=(out['Actual home margin']-out['Roster experimental home margin']).abs()
    return out

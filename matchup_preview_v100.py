"""Courtside V100: display-only matchup preview, based on available pregame box scores.

Never estimates missing statistics or alters the model's projected spread.
"""
from __future__ import annotations
import math
import streamlit as st


def _num(stats, key):
    if not isinstance(stats, dict) or stats.get('validated') is not True:
        return None
    try:
        x = float(stats[key])
        return x if math.isfinite(x) else None
    except (KeyError, TypeError, ValueError):
        return None


def comparison_rows(away, home, a, h):
    """All shown differences use *observed own-team* statistics; no defensive matchup claims."""
    fields = [
        ('Effective shooting (eFG%)', 'efg_pct', '%', 'higher'),
        ('Three-point shooting', 'three_pct', '%', 'higher'),
        ('Turnovers per game', 'tov_pg', '', 'lower'),
        ('Rebounds per game', 'reb_pg', '', 'higher'),
        ('Assists per game', 'ast_pg', '', 'higher'),
        ('Estimated possessions/game', 'possessions', '', 'context'),
    ]
    rows=[]
    for label, key, unit, prefer in fields:
        x,y = _num(a,key),_num(h,key)
        if x is None and y is None: continue
        edge = None
        if x is not None and y is not None and prefer != 'context':
            delta = x-y
            if abs(delta) >= (1.0 if unit=='%' else 0.5):
                edge = away if (delta>0)==(prefer=='higher') else home
        rows.append({'Metric':label,
                     str(away):f'{x:.1f}{unit}' if x is not None else '—',
                     str(home):f'{y:.1f}{unit}' if y is not None else '—',
                     'Statistical edge':edge or '—'})
    return rows


def render_matchup_preview(away,home,*,away_stats=None,home_stats=None):
    st.markdown('#### Matchup at a glance')
    ag = away_stats.get('boxscore_games',0) if isinstance(away_stats,dict) else 0
    hg = home_stats.get('boxscore_games',0) if isinstance(home_stats,dict) else 0
    st.caption('Current-season pregame box-score averages, not predicted outcomes or opponent-adjusted defensive ratings. '
               'Differences show statistical tendencies, not the model’s reasoning.')
    if not ag and not hg:
        st.info('Matchup statistics will appear once completed-game box scores are available. The existing model forecast remains above.')
        return
    cols=st.columns(2)
    for col,name,stats in ((cols[0],away,away_stats),(cols[1],home,home_stats)):
        count=stats.get('boxscore_games',0) if isinstance(stats,dict) else 0
        eligible=stats.get('eligible_final_games',0) if isinstance(stats,dict) else 0
        with col:
            st.markdown(f'**{name}**')
            if count: st.caption(f'{count} of {eligible} loaded games with box scores')
            else: st.caption('No usable game statistics yet')
    pace=[_num(away_stats,'possessions'),_num(home_stats,'possessions')]
    if all(v is not None for v in pace):
        st.metric('Both teams’ observed average pace',f'{sum(pace)/2:.1f} possessions/game')
        st.caption('Average of their observed possession estimates; not a projected pace for this matchup.')
    rows=comparison_rows(away,home,away_stats,home_stats)
    if rows:
        import pandas as pd
        st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
        st.caption('Higher shooting, rebounding and assist averages and lower turnover averages are descriptive only. '
                   'They are not adjusted for opponent strength or pace; an “edge” is not a predicted advantage.')
    else:
        st.caption('No comparable statistics available yet.')

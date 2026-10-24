"""Courtside presentation placeholders for future validated team-stat pipeline.

No fabricated efficiency estimates: only supplied, numeric, validated values render.
When model work begins, pass a mapping of actual stats for each team.
"""
from __future__ import annotations
import html
import math
import streamlit as st

METRICS = [
    ('adj_o', 'Adjusted offense', 'pts / 100 possessions', True),
    ('adj_d', 'Adjusted defense', 'pts allowed / 100 possessions', False),
    ('adj_em', 'Adjusted net efficiency', 'points / 100 possessions', True),
    ('tempo', 'Tempo', 'possessions / 40 min', None),
]
MATCHUP_STATS = [
    ('adj_o', 'Adjusted offense', 'pts / 100 poss.'),
    ('adj_d', 'Adjusted defense', 'pts allowed / 100 poss.'),
    ('tempo', 'Tempo', 'possessions / 40 min'),
    ('efg_pct', 'Effective FG%', '%'),
    ('tov_pct', 'Turnover rate', '%'),
    ('orb_pct', 'Offensive rebound rate', '%'),
    ('ftr', 'Free-throw rate', 'ratio'),
    ('three_pct', 'Three-point FG%', '%'),
]

def _value(stats, key):
    if not isinstance(stats, dict) or stats.get('validated') is not True:
        return 'Not available yet'
    v = stats.get(key)
    try:
        n = float(v)
        if not math.isfinite(n):
            return 'Not available yet'
        return f'{n:.1f}' + ('%' if key.endswith('_pct') else '')
    except (ValueError, TypeError):
        return 'Not available yet'

def render_team_efficiency(stats=None, *, compact=False):
    st.markdown('#### Offensive & defensive efficiency')
    st.caption('Opponent-adjusted efficiency will appear once the underlying possessions and game statistics are validated. These are not derived from the current power rating.')
    tiles = []
    for key, label, unit, _ in METRICS:
        tiles.append(f'<div class="cs-eff-tile"><div class="cs-eff-label">{html.escape(label)}</div>'
                     f'<div class="cs-eff-value">{html.escape(_value(stats,key))}</div>'
                     f'<div class="cs-eff-unit">{html.escape(unit)}</div></div>')
    st.markdown(_css() + '<div class="cs-eff-grid">' + ''.join(tiles) + '</div>', unsafe_allow_html=True)
    if not compact:
        st.caption('Higher adjusted offense and net efficiency are better; lower adjusted defense is better. Tempo is descriptive, not a strength ranking.')

def render_matchup_stats(away, home, *, away_stats=None, home_stats=None):
    st.markdown('#### Matchup statistics')
    st.caption('Statistics are reserved for the validated efficiency model. Missing values are not estimates or zeros.')
    st.markdown(_css(), unsafe_allow_html=True)
    rows = [f'<div class="cs-eff-compare-head"><span>{html.escape(str(away))}</span><span>Metric</span><span>{html.escape(str(home))}</span></div>']
    for key, label, unit in MATCHUP_STATS:
        rows.append('<div class="cs-eff-compare-row">'
                    f'<span>{html.escape(_value(away_stats,key))}</span>'
                    f'<span><strong>{html.escape(label)}</strong><small>{html.escape(unit)}</small></span>'
                    f'<span>{html.escape(_value(home_stats,key))}</span></div>')
    st.markdown('<div class="cs-eff-compare">' + ''.join(rows) + '</div>', unsafe_allow_html=True)

def _css():
    return '''<style>
    .cs-eff-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin:10px 0 17px}
    .cs-eff-tile{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px;min-width:0}
    .cs-eff-label{color:#64748b;font-size:.78rem}.cs-eff-value{font-weight:700;color:#243449;font-size:1.05rem;margin:8px 0;overflow-wrap:anywhere}
    .cs-eff-unit{color:#8491a4;font-size:.72rem}
    .cs-eff-compare{border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;background:white}
    .cs-eff-compare-head,.cs-eff-compare-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(115px,.95fr) minmax(0,1fr);gap:8px;align-items:center;padding:12px;border-bottom:1px solid #edf1f5}
    .cs-eff-compare-head{background:#f8fafc;color:#34465f;font-size:.8rem;font-weight:650}
    .cs-eff-compare-row:last-child{border-bottom:0}
    .cs-eff-compare-row>span:first-child,.cs-eff-compare-row>span:last-child{color:#23354b;font-size:.79rem;font-weight:550;overflow-wrap:anywhere}
    .cs-eff-compare-row>span:nth-child(2){color:#64748b;font-size:.77rem;text-align:center}
    .cs-eff-compare-row small{display:block;color:#94a3b8;font-size:.65rem;margin-top:3px}
    .cs-eff-compare-row>span:last-child,.cs-eff-compare-head>span:last-child{text-align:right}
    @media(max-width:720px){.cs-eff-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.cs-eff-tile{padding:10px}.cs-eff-compare-row,.cs-eff-compare-head{grid-template-columns:minmax(0,1fr) 105px minmax(0,1fr);gap:4px;padding:10px 6px}.cs-eff-compare-row>span:first-child,.cs-eff-compare-row>span:last-child{font-size:.67rem}}
    </style>'''

"""Courtside advanced-stat presentation slots (no estimated or fabricated numbers).

Pass a mapping with validated=True and numeric entries to populate metrics in a future
statistics pipeline. Missing entries remain 'Not available yet'. No model changes.
"""
from __future__ import annotations
import html
import math
import streamlit as st

EFFICIENCY = [
    ('adj_o', 'Adjusted offense', 'points / 100 possessions'),
    ('adj_d', 'Adjusted defense', 'allowed / 100 possessions'),
    ('adj_em', 'Adjusted net efficiency', 'points / 100 possessions'),
    ('tempo', 'Tempo', 'possessions / 40 minutes'),
]
GROUPS = [
    ('Box-score averages', [
        ('pts_pg', 'Points per game', 'per game'),
        ('reb_pg', 'Rebounds per game', 'per game'),
        ('ast_pg', 'Assists per game', 'per game'),
        ('tov_pg', 'Turnovers per game', 'per game'),
        ('stl_pg', 'Steals per game', 'per game'),
        ('blk_pg', 'Blocks per game', 'per game'),
    ]),
    ('Efficiency & pace', EFFICIENCY + [
        ('off_eff', 'Raw offensive efficiency', 'points / 100 possessions'),
        ('def_eff', 'Raw defensive efficiency', 'allowed / 100 possessions'),
        ('possessions', 'Possessions per game', 'estimated possessions'),
        ('net_eff', 'Raw net efficiency', 'offense minus defense'),
        ('tempo', 'Raw tempo', 'estimated possessions / 40 min'),
    ]),
    ('Shooting', [
        ('efg_pct', 'Effective FG%', '%'),
        ('fg_pct', 'Field goal%', '%'),
        ('two_pct', 'Two-point FG%', '%'),
        ('three_pct', 'Three-point FG%', '%'),
        ('ft_pct', 'Free-throw%', '%'),
        ('ftr', 'Free-throw rate', 'FTA / FGA'),
    ]),
    ('Ball security & playmaking', [
        ('tov_pct', 'Turnover rate', '% of possessions'),
        ('ast_tov', 'Assist-to-turnover ratio', 'assists / turnovers'),
        ('ast_pct', 'Assist rate', '% of made field goals'),
    ]),
    ('Rebounding', [
        ('orb_pct', 'Offensive rebound rate', '% of opportunities'),
        ('drb_pct', 'Defensive rebound rate', '% of opportunities'),
        ('reb_pg', 'Rebounds per game', 'per game'),
    ]),
    ('Recent form', [
        ('last5_wins', 'Wins in last five', 'completed games'),
        ('last10_wins', 'Wins in last ten', 'completed games'),
        ('recent_adj_o', 'Recent adjusted offense', 'points / 100 possessions'),
        ('recent_adj_d', 'Recent adjusted defense', 'allowed / 100 possessions'),
    ]),
]

PERCENT_KEYS = {key for _, rows in GROUPS for key, _, unit in rows if unit.startswith('%') or unit == '% of possessions' or unit == '% of opportunities' or unit == '% of made field goals'}
INTEGER_KEYS = {'last5_wins', 'last10_wins'}


def _value(stats, key):
    if not isinstance(stats, dict) or stats.get('validated') is not True:
        return 'Not available yet'
    try:
        n = float(stats[key])
        if not math.isfinite(n):
            return 'Not available yet'
        if key in INTEGER_KEYS:
            return str(int(n)) if n.is_integer() and n >= 0 else 'Not available yet'
        return f'{n:.1f}' + ('%' if key in PERCENT_KEYS else '')
    except (KeyError, ValueError, TypeError):
        return 'Not available yet'


def _css():
    return '''<style>
    .cs-eff-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin:10px 0 17px}
    .cs-eff-tile{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px;min-width:0}
    .cs-eff-label{color:#64748b;font-size:.78rem}.cs-eff-value{font-weight:700;color:#243449;font-size:1.05rem;margin:8px 0;overflow-wrap:anywhere}
    .cs-eff-unit{color:#8491a4;font-size:.72rem}
    .cs-eff-compare{border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;background:white;margin:8px 0 18px}
    .cs-eff-compare-head,.cs-eff-compare-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(145px,.95fr) minmax(0,1fr);gap:8px;align-items:center;padding:12px;border-bottom:1px solid #edf1f5}
    .cs-eff-compare-head{background:#f8fafc;color:#34465f;font-size:.8rem;font-weight:650}
    .cs-eff-compare-row:last-child{border-bottom:0}
    .cs-eff-compare-row>span:first-child,.cs-eff-compare-row>span:last-child{color:#23354b;font-size:.79rem;font-weight:550;overflow-wrap:anywhere}
    .cs-eff-compare-row>span:nth-child(2),.cs-eff-compare-head>span:nth-child(2){color:#64748b;font-size:.77rem;text-align:center;justify-self:center;width:100%;}
    .cs-eff-compare-row small{display:block;color:#94a3b8;font-size:.65rem;margin-top:3px;text-align:center}
    .cs-eff-compare-row>span:last-child,.cs-eff-compare-head>span:last-child{text-align:right}
    @media(max-width:720px){.cs-eff-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.cs-eff-tile{padding:10px}.cs-eff-compare-row,.cs-eff-compare-head{grid-template-columns:minmax(0,1fr) 105px minmax(0,1fr);gap:4px;padding:10px 6px}.cs-eff-compare-row>span:first-child,.cs-eff-compare-row>span:last-child{font-size:.67rem}}
    /* V185: match Courtside's blue/teal visual identity without full-width cards. */
    .st-key-cs185_matchup_stats {max-width:1120px;margin-inline:auto;width:100%;}
    .st-key-cs185_matchup_stats [data-testid="stExpander"] {border:1px solid #cbdcf1;border-radius:13px;background:#f8fbff;overflow:hidden;}
    .st-key-cs185_matchup_stats [data-testid="stExpander"] summary {background:#e9f1ff;color:#153c79;font-weight:750;}
    .st-key-cs185_matchup_stats .cs-eff-compare {max-width:1040px;margin:10px auto 14px;border:1px solid #cbdcf1;box-shadow:0 2px 8px rgba(18,48,106,.04);}
    .st-key-cs185_matchup_stats .cs-eff-compare-head {background:#173b7b;color:#fff;}
    .st-key-cs185_matchup_stats .cs-eff-compare-head>span {color:#fff;}
    .st-key-cs185_matchup_stats .cs-eff-compare-row:nth-child(odd) {background:#f0f7ff;}
    .st-key-cs185_matchup_stats .cs-eff-compare-row:nth-child(even) {background:#fff;}
    .st-key-cs185_matchup_stats .cs-eff-compare-row>span:nth-child(2) strong {color:#1752a0;font-size:.81rem;}
    .st-key-cs185_matchup_stats .cs-eff-compare-row>span:first-child,
    .st-key-cs185_matchup_stats .cs-eff-compare-row>span:last-child {font-weight:700;color:#153c67;}
    .st-key-cs185_matchup_stats .cs-eff-compare-row:hover {background:#e6f5f3;}
    @media(max-width:720px) {.st-key-cs185_matchup_stats {max-width:100%;}.st-key-cs185_matchup_stats .cs-eff-compare-head,.st-key-cs185_matchup_stats .cs-eff-compare-row {grid-template-columns:minmax(0,1fr) 105px minmax(0,1fr);padding:9px 5px;gap:4px;}}
    </style>'''


def render_team_efficiency(stats=None, *, compact=False):
    st.markdown('#### Offensive & defensive efficiency')
    st.caption('Opponent-adjusted ratings are experimental and populate from verified daily snapshots only. Raw statistics use completed box scores.')
    tiles = []
    for key, label, unit in EFFICIENCY:
        tiles.append(f'<div class="cs-eff-tile"><div class="cs-eff-label">{html.escape(label)}</div>'
                     f'<div class="cs-eff-value">{html.escape(_value(stats,key))}</div>'
                     f'<div class="cs-eff-unit">{html.escape(unit)}</div></div>')
    st.markdown(_css() + '<div class="cs-eff-grid">' + ''.join(tiles) + '</div>', unsafe_allow_html=True)
    if stats and stats.get('adjusted_snapshot'):
        st.caption(f"Experimental adjusted snapshot: {stats['adjusted_snapshot']} · {stats.get('adjusted_games', 0)} qualifying games.")
    st.markdown('##### Raw efficiencies (unadjusted)')
    raw_tiles = []
    for key, label, unit in [
        ('off_eff','Raw offense','points / 100 possessions'),
        ('def_eff','Raw defense','allowed / 100 possessions'),
        ('net_eff','Raw net','points / 100 possessions'),
        ('tempo','Raw tempo','possessions / 40 minutes'),
    ]:
        raw_tiles.append(f'<div class="cs-eff-tile"><div class="cs-eff-label">{html.escape(label)}</div>'
                         f'<div class="cs-eff-value">{html.escape(_value(stats,key))}</div>'
                         f'<div class="cs-eff-unit">{html.escape(unit)}</div></div>')
    st.markdown(_css() + '<div class="cs-eff-grid">' + ''.join(raw_tiles) + '</div>', unsafe_allow_html=True)
    if compact:
        st.caption('Unadjusted box-score estimates; detailed shooting and pace statistics are in Analytics.')
        return
    if stats and stats.get('boxscore_games'):
        st.caption(f"ESPN box scores: {stats['boxscore_games']} of {stats.get('eligible_final_games', 0)} loaded finals; raw efficiency: {stats.get('efficiency_games',0)} games; tempo: {stats.get('tempo_games',0)} regulation games. Estimates are not opponent-adjusted.")
    st.markdown('#### Additional team statistics')
    for title, rows in GROUPS:
        if title == 'Efficiency & pace':
            rows = rows[4:]
        with st.expander(title, expanded=(title == 'Box-score averages')):
            for key, label, unit in rows:
                left, right = st.columns([3, 2], vertical_alignment='center')
                left.write(f'**{label}**  ·  {unit}')
                right.write(_value(stats, key))


def render_matchup_stats(away, home, *, away_stats=None, home_stats=None, postgame=False):
    st.markdown('#### Offense, defense & matchup statistics')
    if postgame:
        st.caption('Postgame box-score averages include the completed matchup when available. Raw statistics are descriptive, not opponent-adjusted ratings.')
    else:
        st.caption('Pregame comparisons use only prior completed games. Current-day adjusted ratings are withheld to prevent future information leakage.')
    if away_stats or home_stats:
        st.caption(f"Efficiency sample: {away} — {(away_stats or {}).get('efficiency_games',0)} games; {home} — {(home_stats or {}).get('efficiency_games',0)} games.")
    st.markdown(_css(), unsafe_allow_html=True)
    with st.container(key="cs185_matchup_stats"):
        for group_index, (group_title, metrics) in enumerate(GROUPS):
            with st.expander(group_title, expanded=(group_index == 0)):
                rows = [f'<div class="cs-eff-compare-head"><span>{html.escape(str(away))}</span><span>Metric</span><span>{html.escape(str(home))}</span></div>']
                for key, label, unit in metrics:
                    rows.append('<div class="cs-eff-compare-row">'
                                f'<span>{html.escape(_value(away_stats,key))}</span>'
                                f'<span><strong>{html.escape(label)}</strong><small>{html.escape(unit)}</small></span>'
                                f'<span>{html.escape(_value(home_stats,key))}</span></div>')
                st.markdown('<div class="cs-eff-compare">' + ''.join(rows) + '</div>', unsafe_allow_html=True)

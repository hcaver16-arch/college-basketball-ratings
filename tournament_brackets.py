"""Verified-format and conservative conference tournament previews.

SEC layout is based on published 2026 formats, pending confirmation of 2027 seed rules.
All seed placements are provisional, never official tiebreak decisions.
"""
from __future__ import annotations
import html
import pandas as pd
import streamlit as st


def is_sec(conference: str) -> bool:
    c = str(conference).casefold().strip()
    return c in {'sec', 'southeastern', 'southeastern conference'}


def sec_16_bracket(standings: pd.DataFrame):
    """Five-round SEC bracket. Source shape matches 2026 men's/women's actual brackets.
    Games 1-4: 9/16, 12/13, 10/15, 11/14.
    Games 5-8: 8/G1, 5/G2, 7/G3, 6/G4.
    Games 9-12: 1/G5, 4/G6, 2/G7, 3/G8.
    Games 13-14: G9/G10 and G11/G12, 15 final.
    """
    if len(standings) != 16:
        return None
    s = {i+1: f'#{i+1} {str(row["Team"])}' for i, (_, row) in enumerate(standings.iterrows())}
    return [
        ('First round', [(s[9],s[16]),(s[12],s[13]),(s[10],s[15]),(s[11],s[14])]),
        ('Second round', [(s[8],'Winner G1'),(s[5],'Winner G2'),(s[7],'Winner G3'),(s[6],'Winner G4')]),
        ('Quarterfinals',[(s[1],'Winner G5'),(s[4],'Winner G6'),(s[2],'Winner G7'),(s[3],'Winner G8')]),
        ('Semifinals',[('Winner G9','Winner G10'),('Winner G11','Winner G12')]),
        ('Championship',[('Winner G13','Winner G14')])
    ]


def render_tournament_bracket(standings: pd.DataFrame, conference: str, league: str):
    """Renders safe, horizontally scrollable HTML bracket; no fabricated winners."""
    if standings is None or standings.empty:
        st.info('No conference team list available for a bracket.')
        return
    if not is_sec(conference):
        st.info('A verified 2026–27 tournament bracket format has not been configured for this conference. Provisional standings remain available above; no official bracket is displayed.')
        return
    rounds = sec_16_bracket(standings)
    if rounds is None:
        st.warning(f'The SEC bracket expects 16 teams, but this view currently has {len(standings)}. Check membership before displaying seeded matchups.')
        return
    st.caption('SEC 16-team staggered-entry format (verified against 2026 tournaments; 2027 bracket rules subject to confirmation). All teams qualify; seeds 1–4 enter the quarterfinals, 5–8 enter in round two, and 9–16 play in round one.')
    st.caption('PROVISIONAL: Seeds follow Courtside loaded-game standings and a rating-based tie display; official conference tiebreakers and any eligibility restrictions are not applied. “Winner” labels are undecided future games.')
    blocks = []
    game_number = 1
    for title, games in rounds:
        cards=[]
        for upper, lower in games:
            cards.append('<div class="cb-game"><div class="cb-game-label">G'+str(game_number)+'</div><div class="cb-team">'+html.escape(upper)+'</div><div class="cb-team">'+html.escape(lower)+'</div></div>')
            game_number += 1
        blocks.append('<div class="cb-round"><div class="cb-round-name">'+html.escape(title)+'</div>'+''.join(cards)+'</div>')
    markup = '''<style>
    .cb-scroll{display:flex;gap:14px;overflow-x:auto;padding:8px 4px 16px;align-items:stretch}
    .cb-round{flex:0 0 205px;display:flex;flex-direction:column;gap:14px}
    .cb-round-name{font-size:13px;font-weight:750;color:#23354b;position:sticky;top:0;background:#f5f6f8;padding:8px;border-radius:7px}
    .cb-game{border:1px solid #dce4ed;border-radius:11px;background:white;overflow:hidden;box-shadow:0 2px 5px rgba(24,44,68,.04)}
    .cb-game-label{padding:6px 10px;background:#edf2f7;color:#65768b;font-size:11px;font-weight:700}
    .cb-team{font-size:12px;color:#1e2d40;padding:9px 10px;min-height:34px;overflow-wrap:anywhere}
    .cb-team+.cb-team{border-top:1px solid #e6edf3}
    </style><div class="cb-scroll">'''+''.join(blocks)+'</div>'
    st.markdown(markup, unsafe_allow_html=True)

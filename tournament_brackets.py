"""Courtside conference tournament bracket previews.

SEC: staggered-entry format verified against 2026 men's and women's events;
2027 eligibility and tiebreakers still require confirmation.
Other conferences: structurally valid, ALL-TEAMS PROVISIONAL single-elimination
illustrations, NOT claimed as the league's actual qualification/bye format.
No winner is forecast, all rankings are provisional.
"""
from __future__ import annotations

import html
import math
import pandas as pd
import streamlit as st


def is_sec(conference: str) -> bool:
    return str(conference).casefold().strip() in {
        'sec', 'southeastern', 'southeastern conference'
    }


def sec_16_bracket(standings: pd.DataFrame):
    if len(standings) != 16:
        return None
    s = {i + 1: f'#{i + 1} {str(row["Team"])}'
         for i, (_, row) in enumerate(standings.iterrows())}
    return [
        ('First round', [(s[9], s[16]), (s[12], s[13]),
                         (s[10], s[15]), (s[11], s[14])]),
        ('Second round', [(s[8], 'Winner G1'), (s[5], 'Winner G2'),
                          (s[7], 'Winner G3'), (s[6], 'Winner G4')]),
        ('Quarterfinals', [(s[1], 'Winner G5'), (s[4], 'Winner G6'),
                           (s[2], 'Winner G7'), (s[3], 'Winner G8')]),
        ('Semifinals', [('Winner G9', 'Winner G10'),
                        ('Winner G11', 'Winner G12')]),
        ('Championship', [('Winner G13', 'Winner G14')]),
    ]


def _seeding_order(size: int) -> list[int]:
    """Standard seeded positions, mirrored inside each successive round."""
    if size < 2 or size & (size - 1):
        raise ValueError('size must be a power of two >= 2')
    ranks = [1, 2]
    while len(ranks) < size:
        new_size = len(ranks) * 2
        ranks = [seed for x in ranks for seed in (x, new_size + 1 - x)]
    return ranks


def provisional_all_teams_bracket(standings: pd.DataFrame):
    """Create a structurally valid seeded bracket with automatic opening byes.

    This is intentionally NOT a conference-specific tournament format.
    Returns round title and matches as (top team, bottom team) pairs.
    """
    if standings is None or standings.empty:
        return []
    count = len(standings)
    if count < 2:
        return []
    size = 1 << (count - 1).bit_length()
    ranks = _seeding_order(size)
    seeded = {i + 1: f'#{i + 1} {str(row["Team"])}'
              for i, (_, row) in enumerate(standings.iterrows())}
    slots = [seeded.get(rank) for rank in ranks]
    rounds = []
    game_no = 0
    round_no = 0
    while len(slots) > 1:
        next_slots = []
        matches = []
        for j in range(0, len(slots), 2):
            top, bottom = slots[j], slots[j + 1]
            if top and bottom:
                game_no += 1
                matches.append((top, bottom, game_no))
                next_slots.append(f'Winner G{game_no}')
            else:
                next_slots.append(top or bottom)
        round_no += 1
        if matches:
            rounds.append((len(slots), matches))
        slots = next_slots
    titles = {1: 'Championship', 2: 'Semifinals', 4: 'Quarterfinals',
              8: 'Round of 16', 16: 'Round of 32', 32: 'Round of 64'}
    return [(titles.get(number // 2, f'Round of {number}'), games)
            for number, games in rounds]


def _render_rounds(rounds):
    blocks = []
    number = 0
    for title, games in rounds:
        cards = []
        for entry in games:
            if len(entry) == 3:
                upper, lower, game_number = entry
            else:
                upper, lower = entry
                number += 1
                game_number = number
            cards.append(
                '<div class="cb-game"><div class="cb-game-label">G'
                + str(game_number)
                + '</div><div class="cb-team">' + html.escape(str(upper))
                + '</div><div class="cb-team">' + html.escape(str(lower))
                + '</div></div>'
            )
        blocks.append(
            '<div class="cb-round"><div class="cb-round-name">'
            + html.escape(str(title)) + '</div>' + ''.join(cards) + '</div>'
        )
    markup = '''<style>
    .cb-scroll{display:flex;gap:14px;overflow-x:auto;padding:8px 4px 16px;align-items:stretch}
    .cb-round{flex:0 0 205px;display:flex;flex-direction:column;gap:14px}
    .cb-round-name{font-size:13px;font-weight:750;color:#23354b;position:sticky;top:0;background:#f5f6f8;padding:8px;border-radius:7px}
    .cb-game{border:1px solid #dce4ed;border-radius:11px;background:white;overflow:hidden;box-shadow:0 2px 5px rgba(24,44,68,.04)}
    .cb-game-label{padding:6px 10px;background:#edf2f7;color:#65768b;font-size:11px;font-weight:700}
    .cb-team{font-size:12px;color:#1e2d40;padding:9px 10px;min-height:34px;overflow-wrap:anywhere}
    .cb-team+.cb-team{border-top:1px solid #e6edf3}
    </style><div class="cb-scroll">''' + ''.join(blocks) + '</div>'
    st.markdown(markup, unsafe_allow_html=True)


def render_tournament_bracket(standings: pd.DataFrame, conference: str, league: str):
    """Render a visual tournament preview in every D1 conference view."""
    if standings is None or standings.empty:
        st.info('No conference teams available for a bracket.')
        return
    if len(standings) < 2:
        st.info('At least two qualifying teams are needed to draw a bracket.')
        return
    if is_sec(conference):
        rounds = sec_16_bracket(standings)
        if rounds is None:
            st.warning(f'The SEC tournament expects 16 teams; found {len(standings)}. Showing an all-teams provisional illustration instead, not the official SEC bracket.')
            rounds = provisional_all_teams_bracket(standings)
        else:
            st.caption('SEC staggered-entry structure based on 2026 men’s/women’s tournament formats: seeds 9–16 enter round one, 5–8 round two, and 1–4 the quarterfinals. Confirm 2027 rules before treating the structure as official.')
    else:
        rounds = provisional_all_teams_bracket(standings)
        st.warning('**Illustrative bracket — not this conference’s official tournament format.** All currently listed teams are included with a standard seeded layout and opening-round byes. Actual tournaments may limit qualifiers, use a different bracket, reseed, or apply different tiebreak rules. Men’s and women’s formats may differ.')
    st.caption('Seed order is provisional and calculated from completed games in the selected schedule window, with Courtside ratings used to display ties. “Winner G…” is a placeholder, not a predicted result. These previews do not advance teams automatically.')
    if rounds:
        _render_rounds(rounds)
    else:
        st.info('A bracket could not be generated for the available standings.')

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
from tournament_rules import select_rule


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


def _named(standings: pd.DataFrame, count: int):
    return {i + 1: f'#{i + 1} {str(row["Team"])}'
            for i, (_, row) in enumerate(standings.head(count).iterrows())}


def staggered_15_bracket(standings: pd.DataFrame):
    """15-team 3/4/4/2/1 progression. Pairings are only illustrative."""
    if len(standings) < 15:
        return []
    s = _named(standings, 15)
    return [
        ('First round', [(s[10], s[15]), (s[11], s[14]), (s[12], s[13])]),
        ('Second round', [(s[8], s[9]), (s[5], 'Winner G3'),
                          (s[7], 'Winner G1'), (s[6], 'Winner G2')]),
        ('Quarterfinals', [(s[1], 'Winner G4'), (s[4], 'Winner G5'),
                           (s[2], 'Winner G6'), (s[3], 'Winner G7')]),
        ('Semifinals', [('Winner G8', 'Winner G9'), ('Winner G10', 'Winner G11')]),
        ('Championship', [('Winner G12', 'Winner G13')]),
    ]


def staggered_18_bracket(standings: pd.DataFrame):
    """18-team 2/4/4/4/2/1 progression. Pairings are illustrative."""
    if len(standings) < 18:
        return []
    s = _named(standings, 18)
    return [
        ('First round', [(s[15], s[18]), (s[16], s[17])]),
        ('Second round', [(s[9], 'Winner G2'), (s[12], s[13]),
                          (s[10], 'Winner G1'), (s[11], s[14])]),
        ('Third round', [(s[8], 'Winner G3'), (s[5], 'Winner G4'),
                         (s[7], 'Winner G5'), (s[6], 'Winner G6')]),
        ('Quarterfinals', [(s[1], 'Winner G7'), (s[4], 'Winner G8'),
                           (s[2], 'Winner G9'), (s[3], 'Winner G10')]),
        ('Semifinals', [('Winner G11', 'Winner G12'), ('Winner G13', 'Winner G14')]),
        ('Championship', [('Winner G15', 'Winner G16')]),
    ]



def stepladder_10_bracket(standings: pd.DataFrame, conference: str):
    """Top-ten stepladder; SWAC official pairings, American pairing preview."""
    if len(standings) < 10:
        return []
    s = _named(standings, 10)
    # Winner references G1..G9 are numbered chronologically across rounds.
    return [
        ('First round', [(s[8], s[9]), (s[7], s[10])]),
        ('Second round', [(s[5], 'Winner G1'), (s[6], 'Winner G2')]),
        ('Quarterfinals', [(s[4], 'Winner G3'), (s[3], 'Winner G4')]),
        ('Semifinals', [(s[1], 'Winner G5'), (s[2], 'Winner G6')]),
        ('Championship', [('Winner G7', 'Winner G8')]),
    ]

def wcc_2027_mens_bracket(standings: pd.DataFrame):
    """Four-round, 10-team WCC 2027 layout; seed pairings illustrative.

    The league has verified the field size, nine games and four rounds.
    Do not describe the specific seed pairings below as official.
    """
    if len(standings) < 10:
        return []
    s = _named(standings, 10)
    return [
        ('First round', [(s[7], s[10]), (s[8], s[9])]),
        ('Quarterfinals', [(s[1], 'Winner G2'), (s[4], s[5]),
                           (s[2], 'Winner G1'), (s[3], s[6])]),
        ('Semifinals', [('Winner G3', 'Winner G4'),
                        ('Winner G5', 'Winner G6')]),
        ('Championship', [('Winner G7', 'Winner G8')]),
    ]


def render_tournament_bracket(standings: pd.DataFrame, conference: str, league: str):
    """Render provisional seeded brackets without implying universal verification."""
    if standings is None or standings.empty or len(standings) < 2:
        st.info('At least two conference teams are needed to draw a bracket.')
        return
    rule = select_rule(conference, league, len(standings))
    if rule is not None and len(standings) > rule.field_size:
        st.info(f'Only the top {rule.field_size} provisional seeds are in this tournament preview; the remaining {len(standings)-rule.field_size} conference teams are excluded. Final qualifying teams and tie orders depend on official rules.')
        standings = standings.head(rule.field_size)
    if rule is None:
        rounds = provisional_all_teams_bracket(standings)
        st.warning('**Illustrative bracket (format not verified for this conference/division).** '
                   'All listed teams are included using standard seeded pairings. '
                   'The actual tournament may exclude teams or assign different byes.')
    elif rule.layout == 'staggered16':
        rounds = sec_16_bracket(standings)
    elif rule.layout == 'staggered15':
        rounds = staggered_15_bracket(standings)
    elif rule.layout == 'stepladder10':
        rounds = stepladder_10_bracket(standings, conference)
    elif rule.layout == 'wcc10':
        rounds = wcc_2027_mens_bracket(standings)
    elif rule.layout == 'staggered18':
        rounds = staggered_18_bracket(standings)
    else:
        rounds = provisional_all_teams_bracket(standings)
    if rule is not None:
        st.caption(f'**{rule.conference} — {rule.evidence}.** {rule.note}')
        st.caption(f'Format reference: {rule.source}')
    st.caption('Standings and seeds are provisional, based on the selected schedule window. '
               'Tiebreakers are not official. Bracket matchups and Winner G placeholders '
               'are previews, not confirmed tournament pairings or projected winners.')
    if rounds:
        _render_rounds(rounds)
    else:
        st.info('A bracket could not be generated for these standings.')

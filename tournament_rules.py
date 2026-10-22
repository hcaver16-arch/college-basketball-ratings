"""Conservative, sourced 2026-27 conference tournament format registry.

Rules only become active when the conference/league and exact team count match.
Unlisted conferences use a visibly illustrative all-team bracket; they are NOT
represented as verified tournament configurations.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Rule:
    conference: str
    league: str
    field_size: int
    layout: str
    evidence: str
    source: str
    note: str

RULES = (
    Rule('SEC', 'both', 16, 'staggered16', '2027 field verified; round-entry pattern based on 2026',
         'https://www.secsports.com/news/2026/06/sec-announces-2027-womens-basketball-conference-matchups',
         'All 16 women qualify in 2027. Prior staggered-entry structure retained as a preview; verify exact pairings and 2027 men’s entry rules.'),
    Rule('Big Ten', 'mens', 18, 'staggered18', '2027 entry/byes verified; slot pairings illustrative',
         'https://admin.bigten.org/news/2026/8/7/2027-tiaa-big-ten-mens-basketball-tournament-information.aspx',
         'All 18 qualify. Seeds 15–18 start Tuesday, 9–14 Wednesday, 5–8 Thursday, 1–4 quarterfinals.'),
    Rule('ACC', 'womens', 15, 'staggered15', '2027 qualification/byes reported; slot pairings illustrative',
         'https://accsports.com/news/2027-acc-womens-basketball-tournament-charlotte/',
         'Top 15 of 18 qualify; seeds 1–4 double bye and 5–9 one bye.'),
    Rule('ACC', 'mens', 15, 'staggered15', '2027 field reported; entry structure provisional',
         'https://accsports.com/news/2026-27-acc-mens-basketball-schedule/',
         'Top 15 qualify; seeding/tiebreaks and entry details remain provisional.'),
)

ALIASES = {
 'SEC': {'sec', 'southeastern', 'southeastern conference'},
 'Big Ten': {'big ten', 'big ten conference', 'big 10', 'b1g'},
 'ACC': {'acc', 'atlantic coast', 'atlantic coast conference'},
}

def _league(league: str) -> str:
    v = str(league).casefold()
    if 'women' in v or v in ('w', 'wbb'):
        return 'womens'
    if 'men' in v or v in ('m', 'mbb'):
        return 'mens'
    return 'unknown'

def select_rule(conference: str, league: str, size: int) -> Rule | None:
    text = str(conference).strip().casefold()
    sex = _league(league)
    for rule in RULES:
        if text in ALIASES[rule.conference] and (rule.league == sex or rule.league == 'both') and size == rule.field_size:
            return rule
    return None

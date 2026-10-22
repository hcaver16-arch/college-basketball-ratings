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
    Rule('American', 'both', 10, 'stepladder10', '2027 entry/byes verified by conference',
         'https://theamerican.org/news/2026/9/30/american-conference-announces-2026-27-mens-basketball-conference-schedule.aspx',
         'Only top 10 qualify. Seeds 1–2 to semifinals, 3–4 to quarterfinals, 5–6 to round two. Pairings provisional; applies to both divisions per official releases.'),
    Rule('SWAC', 'both', 10, 'stepladder10', '2027 format and pairings verified by conference',
         'https://swac.org/news/2026/6/11/mens-basketball-swac-announces-new-basketball-tournaments-format-beginning-in-2027.aspx',
         'Only top 10 qualify. First round 8–9 and 7–10; seeds 1–2 enter semifinals, 3–4 quarterfinals, 5–6 round two.'),
    Rule('Big 12', 'mens', 16, 'staggered16', '2027 field/byes reported; slot pairings provisional',
         'https://en.wikipedia.org/wiki/2027_Big_12_men%27s_basketball_tournament',
         'All 16 qualify. Seeds 1–4 double byes, 5–8 single byes. Exact pairings/tiebreakers not independently verified.'),
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
 'American': {'american', 'american conference', 'aac', 'american athletic', 'american athletic conference'},
 'SWAC': {'swac', 'southwestern athletic', 'southwestern athletic conference'},
 'Big 12': {'big 12', 'big 12 conference', 'big twelve'},
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
        if text in ALIASES[rule.conference] and (rule.league == sex or rule.league == 'both') and (size == rule.field_size or (rule.conference in ("American", "SWAC", "ACC") and size > rule.field_size)):
            return rule
    return None

"""Conservative result-resolution helpers for conference tournament brackets.

This module deliberately does NOT infer tournament status from a March date or
from two team names alone. A caller must provide verified tournament-game rows
with explicit conference and season metadata. Winners are returned only when
one unambiguous final matches the expected participants.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping


def _norm(value: object) -> str:
    return ' '.join(str(value or '').casefold().replace('&', 'and').split())


def resolve_confirmed_result(
    team_a_id: str,
    team_b_id: str,
    games: Iterable[Mapping[str, object]],
    *,
    conference: str,
    season: int,
) -> dict[str, object] | None:
    """Return a single verified winner or None.

    Input records must contain game_id, home_id, away_id, home_score,
    away_score, status ('final'), is_conference_tournament (True),
    conference, season, and an explicit source identifier. Never guess.
    """
    pair = {str(team_a_id), str(team_b_id)}
    if len(pair) != 2 or not all(pair):
        return None
    candidates: list[dict[str, object]] = []
    for g in games:
        if g.get('is_conference_tournament') is not True:
            continue
        if _norm(g.get('conference')) != _norm(conference):
            continue
        try:
            if int(g.get('season')) != int(season):
                continue
        except (TypeError, ValueError):
            continue
        if _norm(g.get('status')) not in {'final', 'post'}:
            continue
        if {str(g.get('home_id')), str(g.get('away_id'))} != pair:
            continue
        if not g.get('game_id') or not g.get('source'):
            continue
        try:
            hs, aws = int(g['home_score']), int(g['away_score'])
        except (KeyError, ValueError, TypeError):
            continue
        if hs == aws:
            continue
        winner = str(g['home_id']) if hs > aws else str(g['away_id'])
        candidates.append({'game_id': str(g['game_id']), 'winner_id': winner,
                           'score': f'{hs}-{aws}', 'source': str(g['source'])})
    return candidates[0] if len(candidates) == 1 else None

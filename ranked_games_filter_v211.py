"""V211: filter game listings by Top 25 teams in the selected ranking source.

AP and Coaches polls contain up to 25 teams. Courtside Power contains the
whole D1 field, so its first 25 teams are the ranked group for this filter.
"""
from collections.abc import Mapping

RANKED_GAME_FILTER_OPTIONS = (
    "All games",
    "At least one Top 25",
    "Both Top 25",
    "Ranked vs unranked",
)


def filter_by_ranked_teams(games, ranks: Mapping, selection: str):
    """Return games matching a chosen Top 25 pairing; never invent missing ranks."""
    if selection not in RANKED_GAME_FILTER_OPTIONS:
        raise ValueError(f"Unknown ranked-team filter: {selection}")
    if selection == "All games":
        return games

    top25_ids = set()
    for team_id, value in ranks.items():
        try:
            rank = int(value)
        except (ValueError, TypeError, OverflowError):
            continue
        if 1 <= rank <= 25:
            top25_ids.add(str(team_id))

    away = games["Away ID"].astype(str).isin(top25_ids)
    home = games["Home ID"].astype(str).isin(top25_ids)
    if selection == "At least one Top 25":
        matches = away | home
    elif selection == "Both Top 25":
        matches = away & home
    else:
        matches = away ^ home
    return games.loc[matches].copy()

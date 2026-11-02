"""V207: format ESPN's actual event venue, never infer a venue from home-court status.

The categorical Venue (Home/Neutral) must stay separate: it is used by
Courtside's home-advantage models, venue filters and NET quadrants.
"""
from __future__ import annotations

UNKNOWN_LOCATION = "Location not announced"
_UNUSABLE = {"", "tbd", "tba", "unknown", "none", "null", "nan", "n/a", "-", "—"}


def _safe_part(value):
    """Normalize field values from an optional, undocumented ESPN venue object."""
    if not isinstance(value, str):
        return ""
    part = " ".join(value.split())
    return part if part.casefold() not in _UNUSABLE else ""


def game_location_from_espn(event, competition):
    """Arena, city and state when ESPN provides them; never guess home arenas.

    ESPN commonly publishes competitions[].venue.fullName and
    competitions[].venue.address.city/state. Some events put the venue at
    event level; those are treated as an explicit fallback.
    """
    for source in (competition, event):
        if not isinstance(source, dict):
            continue
        venue = source.get("venue")
        if not isinstance(venue, dict):
            continue
        name = _safe_part(venue.get("fullName")) or _safe_part(venue.get("name")) or _safe_part(venue.get("displayName"))
        address = venue.get("address")
        if not isinstance(address, dict):
            address = {}
        city = _safe_part(address.get("city"))
        state = _safe_part(address.get("state")) or _safe_part(address.get("stateCode"))
        country = _safe_part(address.get("country"))
        locality = city
        if state:
            locality = f"{city}, {state}" if city else state
        elif country and country.upper() not in ("US", "USA", "UNITED STATES"):
            locality = f"{city}, {country}" if city else country
        if name and locality:
            return f"{name} · {locality}"
        if name or locality:
            return name or locality
    return UNKNOWN_LOCATION


def display_game_location(game):
    """Safe formatting for game rows that predate the V207 column."""
    value = game.get("Game location") if hasattr(game, "get") else None
    return _safe_part(value) or UNKNOWN_LOCATION

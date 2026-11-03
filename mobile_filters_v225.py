"""Courtside V225: mobile-first filter density, no browser components required.

Streamlit exposes the initiating WebSocket's request headers via st.context.
Phone UA/client hints are best-effort; users can override in Settings.
Widget keys and selection state are never duplicated between layouts.
"""
from __future__ import annotations


def mobile_client(headers) -> bool:
    """Best-effort phone/tablet detection. Never interpret headers as identity."""
    if not headers:
        return False
    try:
        # Streamlit's headers are case-insensitive; plain dicts used in tests
        # or alternative reverse proxies may not be.
        hint = str(headers.get("sec-ch-ua-mobile") or headers.get("Sec-CH-UA-Mobile") or "").strip().lower()
        agent = str(headers.get("user-agent") or headers.get("User-Agent") or "").lower()
    except (AttributeError, TypeError, ValueError):
        return False
    if hint == "?1":
        return True
    if hint == "?0":
        # Apple browsers typically omit client hints; other desktop hints
        # should not be overridden by an incidental "mobile" UA token.
        return False
    return any(token in agent for token in (
        "iphone", "ipod", "ipad", "mobile", "windows phone",
    ))


def compact_filters_enabled():
    """One override shared by Games, Rankings, Conferences and Strength."""
    import streamlit as st
    if "courtside_compact_filters" in st.session_state:
        return bool(st.session_state["courtside_compact_filters"])
    try:
        return mobile_client(st.context.headers)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return False


GAME_DEFAULTS = (
    ("cs210_game_rank_source", "AP Top 25"),
    ("cs211_ranked_game_filter", "All games"),
    ("cs188_matchup_scope", "All games"),
    ("courtside_games_sort_v182", "Tipoff order"),
    ("v12_game_team", "All teams"),
    ("v12_game_conf", "All conferences"),
    ("v12_game_venue", "Any location"),
    ("games_net_quadrant", "All"),
    ("games_net_side", "Either team"),
    ("games_net_q1", False),
)


def active_game_filters(state) -> tuple[str, ...]:
    """Show active-filter feedback while mobile controls are collapsed."""
    labels = {
        "cs210_game_rank_source": "Rankings",
        "cs211_ranked_game_filter": "Ranked matchups",
        "cs188_matchup_scope": "D1 matchups",
        "courtside_games_sort_v182": "Sort",
        "v12_game_team": "Team",
        "v12_game_conf": "Conference",
        "v12_game_venue": "Venue",
        "games_net_quadrant": "NET quadrant",
        "games_net_side": "NET side",
        "games_net_q1": "Q1 only",
    }
    return tuple(labels[key] for key, default in GAME_DEFAULTS
                 if state.get(key, default) != default)


def active_filter_caption(state, keys: tuple[tuple[str, object, str], ...]) -> str:
    active = [label for key, default, label in keys if state.get(key, default) != default]
    return " · ".join(active) if active else "Default filters"

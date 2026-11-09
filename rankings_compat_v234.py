"""Compatibility guard for Streamlit hot-reloaded Rankings pages.

A live app.py rerun can retain the older imported rankings_ui.render_rankings
without the new `movement` parameter. Inspect the callable before invoking;
never swallow a real TypeError raised by the renderer itself.
"""
from __future__ import annotations

from inspect import Parameter, signature


def render_rankings_compatible(renderer, ratings, preliminary, league, verified_d1_ids, *, movement=None):
    parameters = signature(renderer).parameters
    accepts_movement = (
        "movement" in parameters or
        any(p.kind == Parameter.VAR_KEYWORD for p in parameters.values())
    )
    if accepts_movement:
        return renderer(ratings, preliminary, league, verified_d1_ids, movement=movement)
    return renderer(ratings, preliminary, league, verified_d1_ids)

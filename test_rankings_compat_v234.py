"""V234: rankings work across cached pre-V233 and current render signatures."""
import ast
from pathlib import Path

from rankings_compat_v234 import render_rankings_compatible

app = Path("app.py").read_text()
ast.parse(app)
assert "from rankings_compat_v234 import render_rankings_compatible" in app
assert "render_rankings_compatible(" in app
assert "movement=changes" in app
assert "latest_movement(team_ratings, load_history(SPORTS[league]))" in app

rating = object()
roster = object()
ids = {"1", "2"}
changes = object()
called = []

def old_renderer(r, p, league, d1):
    called.append(("old", r, p, league, d1))
    return "legacy UI"

def new_renderer(r, p, league, d1, movement=None):
    called.append(("new", r, p, league, d1, movement))
    return "current UI"

def flexible_renderer(r, p, league, d1, **kwargs):
    called.append(("flexible", kwargs))
    return "flexible UI"

assert render_rankings_compatible(old_renderer, rating, roster, "Men's", ids, movement=changes) == "legacy UI"
assert called[-1] == ("old", rating, roster, "Men's", ids)
assert render_rankings_compatible(new_renderer, rating, roster, "Women's", ids, movement=changes) == "current UI"
assert called[-1] == ("new", rating, roster, "Women's", ids, changes)
assert render_rankings_compatible(flexible_renderer, rating, roster, "Men's", ids, movement=changes) == "flexible UI"
assert called[-1] == ("flexible", {"movement": changes})

def broken_renderer(r, p, league, d1, movement=None):
    raise TypeError("real failure inside renderer")

try:
    render_rankings_compatible(broken_renderer, rating, roster, "Men's", ids, movement=changes)
except TypeError as err:
    assert str(err) == "real failure inside renderer"
else:
    raise AssertionError("Real rendering errors must not be hidden")

print("V234 cached legacy/current Rankings signatures and error propagation passed")

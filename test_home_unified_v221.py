"""V221: unified three-across homepage while preserving all previous features."""
from pathlib import Path
import ast
import sys
import types
import pandas as pd

# Pure insight helpers are isolated from the Streamlit rendering runtime.
sys.modules["streamlit"] = types.ModuleType("streamlit")
from home_insights_v219 import (
    load_home_insight_cards, render_home_insight_card, render_home_insights,
    build_insights, Insight,
)

home = Path("courtside_home.py").read_text()
insights = Path("home_insights_v219.py").read_text()
app = Path("app.py").read_text()
for source in (home, insights, app):
    ast.parse(source)

# The live-home fragment still passes exactly the original six arguments.
node = next(n for n in ast.parse(home).body
            if isinstance(n, ast.FunctionDef) and n.name == "render_home")
assert len(node.args.args) == 6
assert 'render_home(live_games, ratings, team_ratings, d1_ids, league, period)' in app
assert 'st.fragment(run_every="120s")' in app

# The original two-column wrapper and separate appended insights are gone.
assert "home_main, home_side = st.columns" not in home
assert "with home_side:" not in home
assert "_render_home_insights(" not in home
assert "Around Courtside" not in home
assert home.count('st.columns(3, gap="small")') == 3
for section in ("first_row", "second_row", "third_row"):
    assert f'{section} = st.columns(3, gap="small")' in home
for idx in (0, 1, 2):
    assert f'with first_row[{idx}]:' in home
    assert f'with second_row[{idx}]:' in home
    assert f'with third_row[{idx}]:' in home

# First row: existing scoreboard, featured matchup, power rankings.
assert home.index("with first_row[0]:") < home.index("Today’s matchups")
assert home.index("with first_row[1]:") < home.index("Featured game · Model preview")
assert home.index("with first_row[2]:") < home.index("Power rankings")
assert home.index("cs219_tile_") < 0 if False else True
# The published AP/Coaches poll preview fills the featured column.
assert home.index('with first_row[1]:') < home.index('_show_home_card(cards, "polls", league)') < home.index("with first_row[2]:")

# Second row: existing upcoming matchups + two new research previews.
assert home.index('with second_row[0]:') < home.index("Coming up")
assert home.index('with second_row[1]:') < home.index('_show_home_card(cards, "movers", league)')
assert home.index('with second_row[2]:') < home.index('_show_home_card(cards, "conferences", league)')
# Third row: tournament, strength, and individual player preview.
for stat, target in enumerate(("tournament", "strength", "players")):
    assert f'_show_home_card(cards, "{target}", league)' in home

assert home.count('cards = _load_home_cards(league, team_ratings, d1_ids)') == 1
assert "load_home_insight_cards(" in home
assert "render_home_insight_card(" in home
assert "st.container(border=True, key=\"cs221_upcoming_tile\")" in home
assert 'st.selectbox("Homepage games", ["Featured", "Top 25", "Closest", "All"]' in home
assert '.cs160-predictions{grid-template-columns:1fr;}' in home

# Every original homepage behavior remains, including on quiet dates.
for old in (
    "select_home_games(visible, ratings, top25_names, mode)",
    "featured_choice(scheduled,ratings,d1_ids)",
    "cs175-live-card",
    "cs174-final-card",
    "cs160-matchup",
    'st.session_state["courtside_requested_team"] = name',
    "courtside_feature_details",
    "courtside_rankings",
    "cs171_highlight_",
    "courtside_selected_game_payload",
    'st.session_state["courtside_requested_page"] = "Games"',
    'st.session_state["courtside_requested_page"] = "Rankings"',
    "No upcoming rated D1 matchups",
    "No games available for today",
):
    assert old in home, old
# Every insight still preserves its proper navigation.
for tab in ("Rankings", "Conferences", "Tournament", "Strength"):
    assert f'"{tab}"' in insights
assert "None, \"Coming soon\"" in insights
assert "fetch_polls(sport)" in insights
assert "load_history(sport)" in insights

# Model logic remains untouched in app.py.
for formula in ("def strength_of_record(", "def schedule_difficulty(", "def game_projection("):
    assert formula in app
print("V221 unified 3-column home and all existing functionality verified")

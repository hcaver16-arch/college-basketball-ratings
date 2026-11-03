"""V223: classic homepage panels share the new insight-card surfaces and behavior."""
from pathlib import Path
import ast
import sys
import types
import pandas as pd

home = Path("courtside_home.py").read_text()
insights = Path("home_insights_v219.py").read_text()
app = Path("app.py").read_text()
for source in (home, insights, app):
    ast.parse(source)

# The original four panels now have one keyed white outer card with a top border.
containers = (
    "cs223_tile_games", "cs223_tile_featured",
    "cs223_tile_rankings", "cs223_tile_upcoming",
)
for name in containers:
    assert f'st.container(border=True, key="{name}")' in home, name
    assert f"st-key-{name}" in home or 'st-key-cs223_tile_' in home
assert home.count('with st.container(border=True, key="cs223_tile_') == 4
assert "border-top:3px solid #2b69b9" in home
assert "background:#fff!important" in home
assert ".st-key-cs223_tile_featured" in home
assert ".st-key-cs223_tile_rankings" in home
assert ".st-key-cs223_tile_upcoming" in home

# Use exactly the same header/subtitle hierarchy as the six V219 insight tiles.
assert "cs219-card-head" in home and "cs219-sub" in home
for heading in (
    "Today’s matchups", "Featured game · Model preview",
    "Power rankings", "Coming up",
):
    assert f'_classic_home_card_heading("{heading}"' in home
assert 'f"<strong>{html.escape(title)}</strong>"' not in home  # markup uses safe literal strings
assert "html.escape(title)" in home and "html.escape(subtitle)" in home
assert "html.escape(badge)" in home
assert 'st.container(height=320,border=False)' in home
assert 'st.container(border=False, key="cs222_rankings_list")' in home
assert 'st.container(border=False, key="cs221_upcoming_tile")' in home
assert 'with st.container(border=False):' in home

# Three separate vertical columns stay independent, without the old row gaps.
assert home.count('home_columns = st.columns(3, gap="small")') == 1
assert home.count('with home_columns[0]:') == 1
assert home.count('with home_columns[1]:') == 1
assert home.count('with home_columns[2]:') == 1
assert "first_row = st.columns" not in home
assert "second_row = st.columns" not in home
assert "third_row = st.columns" not in home

# Keep the full game/ratings behavior without recalculating model values.
for marker in (
    "featured_choice(scheduled,ratings,d1_ids)",
    "select_home_games(visible, ratings, top25_names, mode)",
    "row[\"Status\"] == \"Live\"",
    "row[\"Status\"] == \"Final\"",
    "cs170_game_filter",
    "cs170_all_games",
    "courtside_feature_details",
    "cs171_highlight_",
    "st.session_state['courtside_selected_game']",
    "courtside_selected_game_payload",
    'st.session_state["courtside_requested_team"] = name',
    "courtside_rankings",
    "_show_home_card(cards, \"polls\", league)",
    "_show_home_card(cards, \"movers\", league)",
    "_show_home_card(cards, \"conferences\", league)",
    "_show_home_card(cards, \"tournament\", league)",
    "_show_home_card(cards, \"strength\", league)",
    "_show_home_card(cards, \"players\", league)",
):
    assert marker in home, marker
assert "use_container_width=True" in home
assert "load_home_insight_cards(" in home
assert "render_home_insight_card(" in insights
assert "fetch_polls(sport)" in insights
assert "load_history(sport)" in insights
assert 'render_home(live_games, ratings, team_ratings, d1_ids, league, period)' in app
fn = next(n for n in ast.parse(home).body if isinstance(n, ast.FunctionDef) and n.name == "render_home")
assert len(fn.args.args) == 6
assert "Coming soon" in insights

# No change to Courtside's existing modeling, selection, or score definitions.
for marker in ("def strength_of_record(", "def schedule_difficulty(", "def game_projection("):
    assert marker in app
print("V223 all old home panels match insight tiles without changing game/model behavior")

"""V222: independent homepage columns and tighter internal list spacing."""
from pathlib import Path
import ast

home = Path("courtside_home.py").read_text()
insights = Path("home_insights_v219.py").read_text()
app = Path("app.py").read_text()
for src in (home, insights, app):
    ast.parse(src)

tree = ast.parse(home)
fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "render_home")
assert len(fn.args.args) == 6  # hot reload and live-home integration stay compatible
assert 'render_home(live_games, ratings, team_ratings, d1_ids, league, period)' in app
assert '@st.fragment(run_every="120s")' in app

# A single three-wide set of columns, NOT three height-matched horizontal rows.
assert home.count('home_columns = st.columns(3, gap="small")') == 1
for old in ("first_row = st.columns", "second_row = st.columns", "third_row = st.columns",
            "home_main, home_side = st.columns", "_render_home_insights("):
    assert old not in home, old
for idx in (0, 1, 2):
    assert home.count(f"with home_columns[{idx}]:") == 1

# Each column flows vertically, filling the spaces shown in the screenshots.
left = home.split("with home_columns[0]:", 1)[1].split("with home_columns[1]:", 1)[0]
center = home.split("with home_columns[1]:", 1)[1].split("with home_columns[2]:", 1)[0]
right = home.split("with home_columns[2]:", 1)[1]
assert left.index("Today’s matchups") < left.index("Coming up")
assert center.index("Featured game · Model preview") < center.index('_show_home_card(cards, "polls", league)')
assert center.index('_show_home_card(cards, "polls", league)') < center.index('_show_home_card(cards, "movers", league)')
assert '_show_home_card(cards, "strength", league)' in center
assert right.index("Power rankings") < right.index('_show_home_card(cards, "conferences", league)')
assert '_show_home_card(cards, "tournament", league)' in right
assert '_show_home_card(cards, "players", league)' in right

# Rankings and upcoming rows no longer use a tall native divider on every item.
assert 'st.container(border=True, key="cs222_rankings_list")' in right
assert "st.container(border=True, key=\"cs221_upcoming_tile\")" in left
assert 'st.markdown(\'<div class="cs222-divider"></div>\', unsafe_allow_html=True)' in home
# Preserve scoreboard separators, but not oversized dividers between Coming Up entries.
coming_up = left.split("# Avoid repeating the featured game", 1)[1]
assert "st.divider()" not in coming_up
assert "st.divider()" not in right
assert ".st-key-cs222_rankings_list [data-testid=\"stVerticalBlock\"]" in home
assert ".st-key-cs221_upcoming_tile [data-testid=\"stVerticalBlock\"]" in home
assert "min-height:32px" in home
# Matchups label is above optional Featured/Top25/Closest/All filter.
assert left.index("Today’s matchups") < left.index('st.selectbox("Homepage games"')

# Keep every original interactive workflow intact.
for keep in (
    "featured_choice(scheduled,ratings,d1_ids)",
    "st.container(height=320,border=True)",
    'row["Status"] == "Live"',
    'row["Status"] == "Final"',
    "courtside_feature_details",
    "cs170_all_games",
    "cs171_highlight_",
    "courtside_selected_game_payload",
    'st.session_state["courtside_requested_team"] = name',
    "cs177_team_",
    "courtside_rankings",
    "_load_home_cards(league, team_ratings, d1_ids)",
    "No games available for today",
    "No upcoming rated D1 matchups",
):
    assert keep in home, keep

# No new player statistics or recalculated models.
assert "load_history(sport)" in insights
assert "fetch_polls(sport)" in insights
assert "Coming soon" in insights
for function in ("def strength_of_record(", "def schedule_difficulty(", "def game_projection("):
    assert function in app
print("V222 independent columns, compact list spacing and page behavior validated")

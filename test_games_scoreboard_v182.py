"""V182 unified scoreboard regression checks."""
import ast
from pathlib import Path
app=Path("app.py").read_text()
ast.parse(app)
assert '["All", "Live", "Upcoming", "Final"]' in app
assert 'default="All", key="courtside_games_status_v182"' in app
assert 'shown["Status"] == "Live"' in app
assert 'shown["Status"] == "Scheduled"' in app
assert 'shown["Status"] == "Final"' in app
assert '["Tipoff order", "Live games first"]' in app
assert '"_live_first"' in app
assert 'st.session_state["courtside_selected_game_payload"] = game.to_dict()' in app
assert 'game_records(record_schedule, game)' in app
assert 'render_matchup(' in app
assert 'cs_calendar_anchor' in app
assert 'NET quadrant filters' in app
assert 'Download filtered games CSV' in app
assert 'st.markdown(f"### {away_score} – {home_score}")' in app
print("V182 unified scoreboard checks passed")

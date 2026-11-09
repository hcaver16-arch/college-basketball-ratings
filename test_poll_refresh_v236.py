"""V236: make new AP/Coaches polls visible promptly without model changes."""
import ast
from pathlib import Path

app = Path("app.py").read_text()
polls = Path("published_polls_v137.py").read_text()
ast.parse(app)
tree = ast.parse(polls)

fns = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "fetch_polls"]
assert len(fns) == 1
decorators = [ast.unparse(x) for x in fns[0].decorator_list]
assert any("st.cache_data" in d and "ttl=15 * 60" in d for d in decorators), decorators
assert "cached up to 15 minutes" in polls
assert "ESPN may post new polls after their official release" in polls
assert 'render_polls(league, team_ratings, poll_choice="AP Top 25")' in app
assert 'render_polls(league, team_ratings, poll_choice="Coaches Poll")' in app
assert "cs236_refresh_ap_" in app
assert "cs236_refresh_coaches_" in app

app_tree = ast.parse(app)
rankings = [node for node in app_tree.body if isinstance(node, ast.If)
            and ast.unparse(node.test) == "selected_section == 'Rankings'"]
assert len(rankings) == 1
segment = ast.get_source_segment(app, rankings[0])
assert segment.count("fetch_polls.clear()") == 2
assert segment.count("st.rerun()") == 2
assert segment.count('st.button("↻ Check for updated') == 2
# Refreshes must not touch the power model or saved forecasts.
assert "daily_ratings.run" not in segment
assert "rating_engine" not in segment
assert "prediction_archive" not in segment
print("V236 short cache TTL, independent poll refresh buttons, and read-only behavior passed")

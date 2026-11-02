"""V211: synthetic regression tests for ranked matchup filtering."""
import pandas as pd
from ranked_games_filter_v211 import RANKED_GAME_FILTER_OPTIONS, filter_by_ranked_teams

games = pd.DataFrame([
    {"Game ID": "1", "Away ID": "10", "Home ID": "20"},  # both Top 25
    {"Game ID": "2", "Away ID": "10", "Home ID": "30"},  # one Top 25
    {"Game ID": "3", "Away ID": "30", "Home ID": "40"},  # neither
    {"Game ID": "4", "Away ID": "50", "Home ID": "10"},  # one Top 25
])
ranks = {"10": 1, "20": 25, "30": 26, "40": None, "50": "missing"}
def ids(option, mapping=ranks):
    return filter_by_ranked_teams(games, mapping, option)["Game ID"].tolist()

assert ids("All games") == ["1", "2", "3", "4"]
assert ids("At least one Top 25") == ["1", "2", "4"]
assert ids("Both Top 25") == ["1"]
assert ids("Ranked vs unranked") == ["2", "4"]
assert ids("At least one Top 25", {}) == []
assert ids("Both Top 25", {}) == []
assert ids("Ranked vs unranked", {}) == []
assert len(RANKED_GAME_FILTER_OPTIONS) == 4
try:
    ids("Invalid")
    raise AssertionError("Invalid filter must raise")
except ValueError:
    pass

from pathlib import Path
import ast
app = Path("app.py").read_text()
ast.parse(app)
assert "cs211_ranked_game_filter" in app
assert "filter_by_ranked_teams(shown, rank_lookup" in app
assert 'rank_source != "Hide rankings"' in app
print("V211 ranked-games filter checks passed")

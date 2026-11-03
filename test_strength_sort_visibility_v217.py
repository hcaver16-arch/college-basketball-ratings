"""V217: make SOR sort changes visible without mislabeling model ranks."""
import ast
from pathlib import Path
import sys
import types
import pandas as pd

sys.modules["streamlit"] = types.ModuleType("streamlit")
from strength_comparison_v215 import prepare_strength_rows, team_card_markup

rows = pd.DataFrame([
    {"Team ID":"10","Team":"Alpha","Conference":"ACC",
     "SOR score":1.2, "Wins above expected":0.12, "SOR games":1,
     "SOR rank (provisional)":pd.NA},
    {"Team ID":"20","Team":"Beta","Conference":"SEC",
     "SOR score":0.7, "Wins above expected":0.36, "SOR games":3,
     "SOR rank (provisional)":pd.NA},
    {"Team ID":"30","Team":"Gamma","Conference":"SEC",
     "SOR score":0.5, "Wins above expected":0.2, "SOR games":6,
     "SOR rank (provisional)":4},
])

def sort(field, **filters):
    return prepare_strength_rows(
        rows, kind="sor", score_col="SOR score", sort_col=field, **filters
    )

score = sort("SOR score")
above = sort("Wins above expected")
games = sort("SOR games")
assert score["Team ID"].tolist() == ["10", "20", "30"]
assert above["Team ID"].tolist() == ["20", "30", "10"]
assert above["_display_sort_position"].tolist() == [1.0, 2.0, 3.0]
assert games["Team ID"].tolist() == ["30", "20", "10"]
assert games["_display_sort_position"].tolist() == [1.0, 2.0, 3.0]
# Global display position remains unchanged when shared filters are active.
sec = sort("Wins above expected", conference="SEC")
assert sec["Team ID"].tolist() == ["20", "30"]
assert sec["_display_sort_position"].tolist() == [1.0, 2.0]
one = sort("Wins above expected", query="Alpha")
assert one.iloc[0]["_display_sort_position"] == 3

ranked_by_sor = team_card_markup(score.iloc[0], "sor", "SOR score", False)
assert "#1*" in ranked_by_sor
assert "1.20" in ranked_by_sor
assert "†" not in ranked_by_sor

by_wae = team_card_markup(
    above.iloc[0], "sor", "SOR score", False, sort_col="Wins above expected"
)
assert "#1†" in by_wae
assert "+0.36" in by_wae
assert "SOR 0.70" in by_wae
assert "Wins above expected position" in by_wae
assert "teamlogos/" not in by_wae

by_games = team_card_markup(
    games.iloc[0], "sor", "SOR score", False, sort_col="SOR games"
)
assert "#1†" in by_games
assert "SOR 0.50" in by_games
assert '>6</div>' in by_games
# A qualified SOR rank must reappear when sorting by SOR again.
assert "#4" in team_card_markup(score.iloc[2], "sor", "SOR score", False)

# With one rated completed game, both sorts can have identical team order.
# Changing the choice must still visibly switch displayed metric and position type.
one_game = pd.DataFrame([
    {"Team ID":"1","Team":"One","Conference":"ACC","SOR score":0.6,
     "Wins above expected":0.65,"SOR games":1,"SOR rank (provisional)":pd.NA},
    {"Team ID":"2","Team":"Two","Conference":"ACC","SOR score":0.4,
     "Wins above expected":0.55,"SOR games":1,"SOR rank (provisional)":pd.NA},
])
score1 = prepare_strength_rows(one_game,kind="sor",score_col="SOR score",sort_col="SOR score")
wae1 = prepare_strength_rows(one_game,kind="sor",score_col="SOR score",sort_col="Wins above expected")
assert score1["Team ID"].tolist() == wae1["Team ID"].tolist()
assert "0.60" in team_card_markup(score1.iloc[0], "sor", "SOR score", False)
assert "+0.65" in team_card_markup(wae1.iloc[0], "sor", "SOR score", False,sort_col="Wins above expected")

source = Path("strength_comparison_v215.py").read_text()
ast.parse(source)
assert "available_options = {" in source
assert 'if col == "Team" or col in base.columns' in source
assert "sort_col=available_options[sort_label]" in source
assert "† = selected sort position" in source
print("V217 SOR alternate sorting and visible values passed")

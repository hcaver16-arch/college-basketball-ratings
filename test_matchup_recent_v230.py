"""V230: matchup form uses season-to-date finals, not a one-day Games filter."""
import ast
from pathlib import Path

import pandas as pd

source = Path("matchup_analysis.py").read_text()
app_source = Path("app.py").read_text()
tree = ast.parse(source)
ast.parse(app_source)

funcs = [f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name == "_recent"]
assert len(funcs) == 1
env = {"pd": pd}
exec(compile(ast.Module(body=funcs, type_ignores=[]), "matchup_analysis.py", "exec"), env)
recent = env["_recent"]

def fixture(gid, day, home, homeid, away, awayid, hs, aws, status="Final"):
    return {"Game ID": gid, "Date": day, "Time (ET)": "7:00 PM",
            "Home": home, "Home ID": homeid, "Away": away, "Away ID": awayid,
            "Home score": hs, "Away score": aws, "Status": status}

season = pd.DataFrame([
    fixture("first", "2026-11-02", "Towson Tigers", "119", "Opponent A", "1", 81, 65),
    fixture("second", "2026-11-03", "Opponent B", "2", "Utah Utes", "254", 72, 85),
    fixture("missing", "2026-11-04", "Towson Tigers", "119", "Opponent C", "3", None, None),
    fixture("matchup", "2026-11-05", "Utah Utes", "254", "Towson Tigers", "119", None, None, status="Scheduled"),
    fixture("later", "2026-11-07", "Towson Tigers", "119", "Opponent D", "4", 60, 99),
])
selected_day = season[season["Game ID"] == "matchup"].copy()
assert not recent(selected_day, "119"), "One-day schedule should lack prior results"
towson = recent(season, "119", as_of="2026-11-05")
utah = recent(season, "254", as_of="2026-11-05")
assert towson == ["W 81–65 vs Opponent A (2026-11-02)"], towson
assert utah == ["W 85–72 vs Opponent B (2026-11-03)"], utah
assert "2026-11-07" not in " ".join(towson)
assert not recent(season, "119", as_of="2026-11-02"), "Pregame must not include same-day finals"

# Scored final may include the current matchup only after it is completed.
final_season = season.copy()
final_season.loc[final_season["Game ID"] == "matchup", ["Status", "Away score", "Home score"]] = ["Final", 83, 77]
postgame = recent(final_season, "119", as_of="2026-11-05", include_as_of=True)
assert postgame[0] == "W 83–77 vs Utah Utes (2026-11-05)", postgame

assert "recent_source = stats_games if isinstance(stats_games, pd.DataFrame) else games" in source
assert "recent_away = _recent(recent_source, aid," in source
assert "recent_home = _recent(recent_source, hid," in source
assert "for label, recent in ((away, recent_away), (home, recent_home))" in source
assert "for col, name, results in ((a, away, recent_away), (h, home, recent_home))" in source
assert "stats_games=record_schedule" in app_source
print("V230 season recent form, score integrity, and matchup cutoff passed")

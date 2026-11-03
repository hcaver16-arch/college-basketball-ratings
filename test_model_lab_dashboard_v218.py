"""V218 Model Lab overview, navigation, and unchanged research workflows."""
from pathlib import Path
import ast
import sys
import types

import pandas as pd

# Importing the read-only overview should not need a Streamlit runtime.
sys.modules["streamlit"] = types.ModuleType("streamlit")
from model_lab_center_v218 import (
    SECTIONS,
    build_model_lab_snapshot,
    render_model_lab_header,
    render_model_lab_overview,
)

assert SECTIONS == (
    "Overview", "Performance", "Predictions", "Roster Research", "Advanced Tools"
)
games = pd.DataFrame([
    {
        "Game ID": "1", "Game start UTC": "2026-11-02T20:00:00Z",
        "First forecast UTC": "2026-11-02T14:00:00Z",
        "Baseline home margin": 4, "Actual home margin": 8,
        "Matchup class": "D1 vs D1",
    },
    {
        "Game ID": "2", "Game start UTC": "2026-11-03T20:00:00Z",
        "First forecast UTC": "2026-11-03T14:00:00Z",
        "Baseline home margin": 1, "Actual home margin": -6,
        "Matchup class": "D1 vs D1",
    },
    {
        "Game ID": "3", "Game start UTC": "2026-11-03T22:00:00Z",
        "First forecast UTC": "2026-11-03T14:00:00Z",
        "Baseline home margin": -2, "Actual home margin": -3,
        "Matchup class": "D1 vs D1",
    },
    {
        "Game ID": "4", "Game start UTC": "2026-11-04T20:00:00Z",
        "First forecast UTC": "2026-11-04T14:00:00Z",
        "Baseline home margin": 5, "Actual home margin": 10,
        "Matchup class": "D1 vs non-D1",
    },
    {
        "Game ID": "5", "Game start UTC": "2026-11-04T20:00:00Z",
        "First forecast UTC": "2026-11-05T14:00:00Z",
        "Baseline home margin": 1, "Actual home margin": 10,
        "Matchup class": "D1 vs D1",
    },
])
forecasts = pd.DataFrame({"Game ID":["1","2","3","4","5","6"]})
s = build_model_lab_snapshot(forecasts, games)
assert s.saved_forecasts == 6
assert s.d1_games == 3
assert s.all_graded == 4
assert s.excluded_invalid_pre_tip == 1
assert s.mae == "4.00", s.mae
assert s.winner_accuracy == "66.7%", s.winner_accuracy
assert s.monthly["Games"].tolist() == [3]
assert s.daily["Games"].tolist() == [1,2]
assert len(s.issues) == 1
assert "excluded" in s.issues[0]
assert s.daily["MAE"].tolist() == [4,4]

# No observed pre-tip games: no invented MAE/accuracy or decorative trends.
empty = build_model_lab_snapshot(pd.DataFrame(), pd.DataFrame())
assert empty.d1_games == 0
assert empty.mae == "—" and empty.winner_accuracy == "—"
assert empty.daily.empty and empty.monthly.empty
unclassified = build_model_lab_snapshot(forecasts, games.drop(columns="Matchup class"))
assert unclassified.d1_games == 0
assert "missing" in unclassified.issues[0]

app = Path("app.py").read_text()
page = Path("model_lab_center_v218.py").read_text()
for src in (app,page,Path("live_performance_v123.py").read_text()):
    ast.parse(src)

# One top-level Model Lab; only the selected workstream is evaluated.
assert app.count('if selected_section == "Model Lab":') == 1
assert 'lab_section = render_model_lab_header(league)' in app
assert 'render_model_lab_overview(SPORTS[league], league, archived_meta)' in app
for name in SECTIONS:
    assert f'lab_section == "{name}"' in app, name

# Must retain all five essential prior research/data workflows.
for marker in (
    "render_opening_game_monitor_v133()",
    "render_prospective_model_lab(division=",
    "render_live_performance_v123()",
    "Automatic prospective prediction archive",
    "Prospective roster model comparison (untrained)",
    "Preliminary roster-adjusted rankings (experimental)",
    "Automatic roster collection progress",
    "Roster data validation & experimental player features",
    "Rosters and sourced player adjustments",
    "Automated roster snapshot audit (experimental)",
    "Returning production — sourced player statistics",
    "Incoming players & possible transfers (experimental)",
    "Calculate current ratings, conference strength, SOS and lines",
    "Run historical out-of-sample test",
    "Run November 2025 preseason comparison",
    "Historical 2025–26 roster reconstruction",
    "roster_effects(roster_file, ids)",
):
    assert marker in app,marker

# Preserve the established power-model and strength formula definitions.
for marker in (
    "def strength_of_record(",
    "def schedule_difficulty(",
    "def game_projection(",
    "def calculate_power(",
    "def make_combined(",
):
    assert marker in app,marker
assert "from live_performance_v123 import _read, _graded, _score" in page
assert "D1 vs D1" in page and "st.line_chart" in page
print("V218 Model Lab dashboard metrics, navigation and workflow preservation passed")

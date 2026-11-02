"""V212 synthetic Conferences page and standings regression checks."""
from pathlib import Path
import ast
import sys
import types

import pandas as pd

sys.modules["streamlit"] = types.ModuleType("streamlit")
from conferences_ui import (
    COMPARE_OPTIONS,
    CONFERENCE_STYLE,
    prepare_conference_summary,
    standings_markup,
)
from conference_standings import standings_for_conference

teams = pd.DataFrame([
    {"Team ID":"1","Team":"Alpha","Conference":"SEC","Current power":11.0,"Rank":1},
    {"Team ID":"2","Team":"Beta","Conference":"SEC","Current power":5.0,"Rank":10},
    {"Team ID":"3","Team":"Gamma","Conference":"Big Ten","Current power":8.0,"Rank":5},
    {"Team ID":"4","Team":"Bad","Conference":"Unknown","Current power":1000.0},
    {"Team ID":"5","Team":"Missing","Conference":"SEC","Current power":float("nan")},
    {"Team ID":"6","Team":"Non-D1","Conference":"Big Ten","Current power":900.0},
    {"Team ID":"1","Team":"Alpha duplicated","Conference":"SEC","Current power":99.0},
])
valid={"1","2","3","4","5"}
rated, summary = prepare_conference_summary(teams,valid)
assert len(rated) == 3
assert summary["Conference"].tolist() == ["Big Ten","SEC"]
assert summary["Teams"].tolist() == [1,2]
assert summary["Power rank"].tolist() == [1,2]
assert summary["Average"].tolist() == [8.0,8.0]
assert summary["Top five"].tolist() == [8.0,8.0]
assert sorted(COMPARE_OPTIONS) == ["Average team power","Median team power","Top-five power"]
assert prepare_conference_summary(teams,set())[0].empty
assert "max-width:700px" in CONFERENCE_STYLE

sec = rated[rated["Conference"]=="SEC"]
unplayed = standings_for_conference(sec, None)
assert unplayed["Conference PCT"].tolist() == [0.0,0.0]
assert unplayed["Team ID"].tolist() == ["1","2"]
assert "Power" in unplayed.columns
assert "—" in standings_markup(unplayed,show_logos=False)
assert "teamlogos/" not in standings_markup(unplayed,show_logos=False)

games = pd.DataFrame([
    {"Game ID":"x","Home ID":"2","Away ID":"1","Status":"Final","Home score":64,"Away score":70},
    {"Game ID":"x","Home ID":"2","Away ID":"1","Status":"Final","Home score":64,"Away score":70},
    {"Game ID":"y","Home ID":"1","Away ID":"3","Status":"Final","Home score":80,"Away score":72},
])
played = standings_for_conference(sec,games)
assert played["Team ID"].tolist() == ["1","2"]
assert played.iloc[0]["Conference W"] == 1
assert played.iloc[1]["Conference L"] == 1
assert played.iloc[0]["Overall W"] == 2
markup = standings_markup(played)
assert "teamlogos/ncaa/500/1.png" in markup
assert "1–0" in markup and "1.000" in markup
injection = played.copy()
injection.loc[0,"Team"] = '<script>alert("x")</script>'
safe = standings_markup(injection, show_logos=False)
assert "<script>" not in safe and "&lt;script&gt;" in safe

app=Path("app.py").read_text()
page=Path("conferences_ui.py").read_text()
for source in (app,page,Path("conference_standings.py").read_text()):
    ast.parse(source)
assert "render_conferences(team_ratings, verified_d1_ids, league, games, period)" in app
for marker in (
    'st.tabs(["Standings", "Power Rankings", "Tournament"])',
    "render_tournament_bracket(standings, selected, league)",
    "cc_breakdown", "cc_back_to_all", "cc_team_",
    "cs212_conference_", "cs212_display", "cs212_table_open",
    "cc_find", "cc_sort", "courtside_logos_enabled",
    "st.columns(3", "Top-five power",
):
    assert marker in page, marker
assert "not official tiebreak results" in page
print("V212 conference cards, standings, tables, mobile styles, and navigation passed")

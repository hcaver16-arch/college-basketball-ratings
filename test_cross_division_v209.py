"""V209 regression: historical scores, shrinkage and safe cross-division UI."""
import ast
from pathlib import Path
import math
import pandas as pd

from cross_division_v209 import estimate, line_for_game, REQUIRED_SAMPLE, load_cross_division_calibration
from build_cross_division_v209 import parse_final, implied_non_d1_strength, fit_d1
assert REQUIRED_SAMPLE>=30

cal={
    "model_version":"v209_empirical_prior_v1",
    "sport":"mens-college-basketball",
    "source_season":"2025-26",
    "source_cutoff_utc":"2026-04-15T00:00:00Z",
    "training_games":150,
    "pooled_non_d1_rating":-24.0,
    "opponents":{"1001":{"games":3,"shrunk_rating":-18.5}},
}
d1={"15","23"}
ratings={"15":4.5,"23":2.0}
game={"Home ID":"15","Away ID":"1001","Home":"Princeton Tigers",
      "Away":"Carnegie Mellon Tartans","Venue":"Home","Status":"Live",
      "Home score":50,"Away score":23}
p=estimate(game,ratings,d1,cal)
assert p is not None
assert p["favorite"]=="Princeton Tigers"
assert p["home_margin"]==26.0
assert p["outside_games"]==3
assert p["confidence"]=="Low"
assert line_for_game(p)=="Princeton Tigers -26.0"
# In-game score NEVER alters a pregame score-independent research estimate.
assert estimate({**game,"Home score":5,"Away score":105},ratings,d1,cal)==p
# Unknown outside-of-DI opponent gets evidence-backed pooled prior.
fresh=estimate({**game,"Away ID":"2002","Away":"Another School"},ratings,d1,cal)
assert fresh["outside_games"]==0 and fresh["home_margin"]==31.5
assert fresh["method"]=="pooled cross-division prior"
# D1 visitor with other home gets opposite HCA.
visitor=estimate({**game,"Home ID":"1001","Away ID":"15","Venue":"Home"},ratings,d1,cal)
assert visitor["home_margin"]==-20.0
neutral=estimate({**game,"Venue":"Neutral"},ratings,d1,cal)
assert neutral["home_margin"]==23.0
# Unknown status or identity cannot be forced into a cross division projection.
assert estimate({**game,"Venue":"Unknown"},ratings,d1,cal) is None
assert estimate({**game,"Away ID":"23"},ratings,d1,cal) is None
assert estimate({**game,"Home ID":"9999","Away ID":"2002"},ratings,d1,cal) is None
assert estimate(game,ratings,{"15","1001"},cal) is None
assert estimate(game,{"15":float("nan")},d1,cal) is None
assert estimate(game,ratings,d1,{**cal,"training_games":1}) is None
assert estimate(game,ratings,d1,{**cal,"model_version":"not_v209"}) is None
assert line_for_game(None)=="No verified cross-DI estimate"

event={
    "id":"cross123","date":"2025-11-05T00:00:00Z",
    "status":{"type":{"completed":True}},
    "competitions":[{
        "neutralSite":False,
        "competitors":[
            {"homeAway":"home","team":{"id":"15","displayName":"D1 example"},"score":"85"},
            {"homeAway":"away","team":{"id":"1001","displayName":"Unknown division example"},"score":"55"}
        ]
    }]
}
g=parse_final(event)
assert g["Status"]=="Final" and g["Home score"]==85
assert g["Venue"]=="Home"
e=implied_non_d1_strength(g,{"15"},{"15":5.0})
assert e==("1001",-22.0),e
g["Venue"]="Neutral"
assert implied_non_d1_strength(g,{"15"},{"15":5.0})==("1001",-25.0)
assert implied_non_d1_strength(g,{"15","1001"},{"15":5.0}) is None
assert implied_non_d1_strength(g,set(),{"15":5.0}) is None
# Other team's home-court direction and 55-point blowout clipping.
reverse={**g,"Home ID":"1001","Away ID":"15","Home score":40,"Away score":90,"Venue":"Home"}
assert implied_non_d1_strength(reverse,{"15"},{"15":5})==("1001",-48.0)
# When an unknown team has no history, the model doesn't invent division or player values.
assert "division" not in p
for file in ("app.py","matchup_analysis.py","cross_division_v209.py","build_cross_division_v209.py"):
    ast.parse(Path(file).read_text())
app=Path("app.py").read_text()
detail=Path("matchup_analysis.py").read_text()
assert "cross_model = load_cross_division_calibration(SPORTS[league])" in app
assert '"Cross-div · " + cross_division_line(experimental)' in app
assert 'league=league, game_projection=game_projection, cross_division_model=cross_model' in app
assert 'cross_projection=estimate_cross_division' in detail
assert "Cross-division estimate · provisional" in detail
assert "Not a locked pregame forecast or a live in-game prediction" in detail
assert "Cross-division games remain excluded from official D1 model evaluation" in detail
assert "f\"{displayed_projection[1]:.1f}%\"" in detail  # Only standard DI card branch
assert "def game_projection(game, ratings):" in app
print("V209 source-driven cross-division signs, no live-score leakage, low confidence and D1 separation passed")

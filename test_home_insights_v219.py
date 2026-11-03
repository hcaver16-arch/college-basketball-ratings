"""V219: three-across homepage, verified metric previews and graceful gaps."""
import ast
import sys
import types
from pathlib import Path
import pandas as pd

# Pure data and HTML helpers don't require a running Streamlit server.
sys.modules["streamlit"] = types.ModuleType("streamlit")
from home_insights_v219 import (
    Insight, rating_movers, strength_spotlight, poll_watch, card_html,
    conference_leaders, projected_front_runners, build_insights,
)

history = pd.DataFrame([
    {"Team ID":"1","Team":"Alpha","Current power":10,"Snapshot date":"2026-11-01"},
    {"Team ID":"2","Team":"Beta","Current power":12,"Snapshot date":"2026-11-01"},
    {"Team ID":"3","Team":"Gamma","Current power":13,"Snapshot date":"2026-11-01"},
    {"Team ID":"4","Team":"NON-D1","Current power":0,"Snapshot date":"2026-11-01"},
    {"Team ID":"1","Team":"Alpha","Current power":12,"Snapshot date":"2026-11-02"},
    {"Team ID":"2","Team":"Beta","Current power":10,"Snapshot date":"2026-11-02"},
    {"Team ID":"3","Team":"Gamma","Current power":13.5,"Snapshot date":"2026-11-02"},
    {"Team ID":"4","Team":"NON-D1","Current power":300,"Snapshot date":"2026-11-02"},
])
ids = {"1","2","3"}
movers, message = rating_movers(history, ids)
assert not message
assert movers == (("↑ Alpha","+2.0"),("↑ Gamma","+0.5"),("↓ Beta","-2.0")),movers
assert "NON-D1" not in str(movers)
waiting, reason = rating_movers(history.iloc[:4], ids)
assert not waiting and "second" in reason
missing, reason = rating_movers(pd.DataFrame(), ids)
assert not missing and "snapshots" in reason

sos = pd.DataFrame([
    {"Team ID":"1","Team":"Alpha","Full SOS":11},
    {"Team ID":"2","Team":"Beta","Full SOS":9},
    {"Team ID":"4","Team":"NON-D1","Full SOS":99},
])
sor = pd.DataFrame([
    {"Team ID":"1","Team":"Alpha","SOR score":0.4,"SOR games":1},
    {"Team ID":"2","Team":"Beta","SOR score":0.9,"SOR games":3},
    {"Team ID":"4","Team":"NON-D1","SOR score":9.9,"SOR games":12},
])
strength, missing_note = strength_spotlight(sos, sor, ids)
assert not missing_note
assert strength == (("SOS · Alpha","+11.0"),("SOR · Beta","0.90 · 3 game(s)"))
assert "NON-D1" not in str(strength)
assert strength_spotlight(pd.DataFrame(),pd.DataFrame(), ids)[0] == ()

polls = {
    "AP Top 25":{"rows":pd.DataFrame([{"Rank":1,"Team":"Top AP"},{"Rank":2,"Team":"Other"}])},
    "Coaches Poll":{"rows":pd.DataFrame([{"Rank":1,"Team":"Top Coaches"}])},
}
leader_rows, missing_note = poll_watch(polls)
assert leader_rows == (("AP #1 · Top AP",""),("Coaches #1 · Top Coaches",""))
assert not missing_note
assert poll_watch({})[0] == ()
assert "unavailable" in poll_watch({})[1]

# Stub existing official data-pipeline methods to ensure preview code uses them
# rather than inventing a different conference or tournament selection model.
called = {}
conf = types.ModuleType("conferences_ui")
def prepare_conf(ratings, verified):
    called["conference"] = (ratings,verified)
    return ratings, pd.DataFrame([
        {"Power rank":1,"Conference":"SEC","Average":14.6},
        {"Power rank":2,"Conference":"Big Ten","Average":12.3},
        {"Power rank":3,"Conference":"ACC","Average":10.7},
    ])
conf.prepare_conference_summary = prepare_conf
sys.modules["conferences_ui"] = conf
bracket = types.ModuleType("bracketology_v138")
def project(ratings, verified, sor):
    called["bracket"] = (ratings,verified,sor)
    return pd.DataFrame([
        {"Overall seed list":2,"Team":"Second"},
        {"Overall seed list":1,"Team":"First"},
        {"Overall seed list":3,"Team":"Third"},
        {"Overall seed list":4,"Team":"Fourth"},
    ]),None
bracket.project_field = project
sys.modules["bracketology_v138"] = bracket

ratings = pd.DataFrame({"Team ID":["1","2","3"],"Current power":[12,10,13]})
conf_rows, msg = conference_leaders(ratings,ids)
assert not msg and conf_rows[0] == ("1. SEC","+14.6")
assert called["conference"][1] == ids
bracket_rows, msg = projected_front_runners(ratings,ids,sor)
assert not msg
assert bracket_rows[0] == ("1. First","Overall")
assert bracket_rows[-1] == ("4. Fourth","Overall")
assert called["bracket"][2] is sor

cards=build_insights(ratings,ids,history,sos,sor,polls)
assert len(cards)==6
assert [c.id for c in cards]==["movers","conferences","tournament","strength","players","polls"]
assert [c.page for c in cards]==["Rankings","Conferences","Tournament","Strength",None,"Rankings"]
assert cards[4].badge=="Coming soon"
assert "2026–27" in cards[4].note
assert cards[4].rows==(("Points per game","—"),("Rebounds per game","—"),("Assists per game","—"))
assert "<" not in card_html(Insight("bad","<script>alert(1)</script>","x",rows=(("A&B","<b>"),)))
assert "&lt;script&gt;" in card_html(Insight("bad","<script>","x"))

bracket.project_field=lambda *args:(pd.DataFrame(),"Found 30 conferences")
no_field, warning=projected_front_runners(ratings,ids,sor)
assert not no_field and "unavailable" in warning

home = Path("courtside_home.py").read_text()
insights = Path("home_insights_v219.py").read_text()
app = Path("app.py").read_text()
for source in (home,insights,app):
    ast.parse(source)
mod=ast.parse(home)
fn=next(node for node in mod.body if isinstance(node,ast.FunctionDef) and node.name=="render_home")
assert len(fn.args.args)==6
assert "def _render_home_insights(" in home
assert home.count("_render_home_insights(league, team_ratings, d1_ids)") == 2
assert home.index("Featured game · Model preview") < home.rindex("_render_home_insights(league, team_ratings, d1_ids)")
assert "st.columns(3, gap=\"small\")" in insights
assert "for offset in (0, 3)" in insights
assert "courtside_requested_page" in insights
assert "fetch_polls(sport)" in insights
assert "load_history(sport)" in insights
print("V219 homepage insight sources, navigation, snapshots, and responsive grid passed")

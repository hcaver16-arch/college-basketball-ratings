"""Synthetic AP/Coaches poll parsing checks."""
import sys, types
import pandas as pd
fake=types.ModuleType("streamlit")
fake.cache_data=lambda **kwargs: lambda x:x
sys.modules["streamlit"]=fake
from published_polls_v137 import parse_polls, poll_kind
assert poll_kind("AP Top 25")=="AP Top 25"
assert poll_kind("USA TODAY Coaches Poll")=="Coaches Poll"
payload={"rankings":[
  {"name":"AP Top 25","date":"2026-10-19","ranks":[
    {"current":1,"team":{"id":"1","displayName":"School A"},"points":500},
    {"current":2,"team":{"id":"2","displayName":"School B"},"points":420}]},
  {"name":"USA TODAY Coaches Poll","ranks":[
    {"current":1,"team":{"id":"1","displayName":"School A"}},
    {"current":2,"team":{"id":"2","displayName":"School B"}}]}]}
d=parse_polls(payload)
assert list(d)==["AP Top 25","Coaches Poll"]
assert d["AP Top 25"]["rows"]["Team ID"].tolist()==["1","2"]
assert d["Coaches Poll"]["rows"]["Rank"].tolist()==[1,2]
assert not parse_polls({"rankings":[]})
print("V137 poll parsing checks passed")

# V194: the two top-level poll tabs must show the requested poll without
# adding a second poll selector inside either tab.
from published_polls_v137 import render_polls
import published_polls_v137 as module
shown, notices = [], []
fake.caption = lambda msg: None
fake.markdown = lambda msg: None
fake.info = notices.append
fake.warning = lambda msg: (_ for _ in ()).throw(AssertionError(msg))
fake.dataframe = lambda frame, **kwargs: shown.append(frame.copy())
fake.radio = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Redundant poll selector"))
fake.segmented_control = lambda *args, **kwargs: "Compact list"
module.fetch_polls = lambda sport: d
render_polls("Men's", pd.DataFrame(), poll_choice="AP Top 25")
assert shown[-1]["Team"].tolist() == d["AP Top 25"]["rows"]["Team"].tolist()
render_polls("Women's", pd.DataFrame(), poll_choice="Coaches Poll")
assert shown[-1]["Team"].tolist() == d["Coaches Poll"]["rows"]["Team"].tolist()
module.fetch_polls = lambda sport: {"AP Top 25": d["AP Top 25"]}
count = len(shown)
render_polls("Men's", pd.DataFrame(), poll_choice="Coaches Poll")
assert len(shown) == count and any("Coaches Poll" in msg for msg in notices)
try:
    render_polls("Men's", pd.DataFrame(), poll_choice="Invalid Poll")
    assert False, "Invalid poll choice should be rejected"
except ValueError:
    pass
print("V194 independent rankings-tab poll checks passed")


# V196: published AP and Coaches tabs get independent ranking tiles.
from contextlib import nullcontext
tile_html, tile_keys, team_buttons, view_keys = [], [], [], []
fake.session_state = {"courtside_logos_enabled": True}
fake.html = tile_html.append
fake.container = lambda **kwargs: (tile_keys.append(kwargs.get("key")) or nullcontext())
fake.columns = lambda count, **kwargs: [nullcontext() for _ in range(count)]
fake.button = lambda label, **kwargs: (team_buttons.append((label, kwargs.get("key"))) or False)
fake.segmented_control = lambda label, options, **kwargs: (
    view_keys.append(kwargs.get("key")) or "Tiles"
)
module.fetch_polls = lambda sport: d
render_polls("Men's", pd.DataFrame(), poll_choice="AP Top 25")
assert len(tile_html) == 2, len(tile_html)
assert "School A" in tile_html[0] and "School B" in tile_html[1]
assert "Poll points" in tile_html[0] and "500" in tile_html[0]
assert "teamlogos/ncaa/500/1.png" in tile_html[0]
assert len(team_buttons) == 2
ap_key = view_keys[-1]
assert "ap_top_25" in ap_key and "mens-college-basketball" in ap_key
assert any(k and "ap_top_25" in k for k in tile_keys)

tile_html.clear()
fake.session_state["courtside_logos_enabled"] = False
render_polls("Men's", pd.DataFrame(), poll_choice="Coaches Poll")
assert len(tile_html) == 2
assert all("teamlogos/" not in card for card in tile_html)
assert all("cr196-initials" in card for card in tile_html)
assert "Coaches Poll" not in tile_html[0]  # No invented data or extra poll selector
assert "coaches_poll" in view_keys[-1] and view_keys[-1] != ap_key

from published_polls_v137 import _poll_tile_markup, _open_poll_team
sample = pd.Series({
    "Rank": 4, "Team": 'A & <B> "School"', "Team ID": "19",
    "Record": "5-0", "Points": 412, "Courtside rank (all rated)": 12,
})
markup = _poll_tile_markup(sample, show_logos=True)
assert "A &amp; &lt;B&gt; &quot;School&quot;" in markup
assert 'A & <B>' not in markup
assert "#4" in markup and "#12" in markup and "412" in markup
assert "teamlogos/ncaa/500/19.png" in markup
assert 'cr196-initials' in _poll_tile_markup(sample, show_logos=False)
missing = pd.Series({"Rank": 1, "Team": "Unknown", "Team ID": "",
                     "Record": "", "Points": None})
unrated = _poll_tile_markup(missing, show_logos=True)
assert "Record unavailable" in unrated
assert "—" in unrated and "teamlogos/" not in unrated

class OpenedTeam(Exception): pass
fake.rerun = lambda: (_ for _ in ()).throw(OpenedTeam())
try:
    _open_poll_team(sample)
except OpenedTeam:
    pass
else:
    raise AssertionError("Team button did not navigate")
assert fake.session_state["courtside_requested_team_id"] == "19"
assert fake.session_state["courtside_page"] == "Teams"
print("V196 independent published poll tiles and team links passed")

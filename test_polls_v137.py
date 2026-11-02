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

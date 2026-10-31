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

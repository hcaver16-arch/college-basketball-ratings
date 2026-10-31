"""V133 synthetic integrity smoke test without touching production archives."""
import ast
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

source=Path("opening_game_monitor_v133.py").read_text()
ast.parse(source)
# Stub streamlit to permit importing the pure summary function in CI.
import sys, types
st=types.ModuleType("streamlit")
st.cache_data=lambda **kwargs: lambda fn: fn
sys.modules["streamlit"]=st
from opening_game_monitor_v133 import summarize
now=pd.Timestamp("2026-11-01T12:00:00Z")
f=pd.DataFrame([
    {"Game ID":"1","Game start UTC":"2026-11-02T00:00:00Z","First forecast UTC":"2026-11-01T00:00:00Z"},
    {"Game ID":"2","Game start UTC":"2026-11-01T00:00:00Z","First forecast UTC":"2026-11-01T01:00:00Z"}
])
r=summarize(f,pd.DataFrame(),{"updated_utc":"2026-11-01T10:00:00Z"},now)
assert r["saved"]==2 and r["pre_tip"]==1 and r["upcoming"]==1
assert any("valid pre-tip" in i for i in r["issues"])
empty=summarize(pd.DataFrame(),pd.DataFrame(),None,now)
assert empty["completed"]==0 and empty["issues"]
assert 'render_opening_game_monitor_v133()' in Path("app.py").read_text()
print("V133 synthetic monitoring tests passed")

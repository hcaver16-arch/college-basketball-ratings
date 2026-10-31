"""V135 synthetic check: pre-tip filtering and exactly paired games."""
import sys,types
import pandas as pd
st=types.ModuleType("streamlit")
sys.modules["streamlit"]=st
from opening_week_evaluation_v135 import opening_week_metrics

data=pd.DataFrame([
{"Game ID":"1","Game start UTC":"2026-11-01T20:00:00Z","First forecast UTC":"2026-11-01T11:00:00Z","Actual home margin":8,"Baseline home margin":5,"Later roster margin":7,"Roster forecast UTC":"2026-11-01T12:00:00Z","Matchup class":"D1 vs D1"},
{"Game ID":"2","Game start UTC":"2026-11-01T21:00:00Z","First forecast UTC":"2026-11-01T22:00:00Z","Actual home margin":-3,"Baseline home margin":-5,"Later roster margin":-4,"Roster forecast UTC":"2026-11-01T19:00:00Z","Matchup class":"D1 vs D1"},
{"Game ID":"3","Game start UTC":"2026-11-01T21:00:00Z","First forecast UTC":"2026-11-01T12:00:00Z","Actual home margin":-4,"Baseline home margin":2,"Later roster margin":-3,"Roster forecast UTC":"2026-11-01T22:00:00Z","Matchup class":"D1 vs D1"}])
r=opening_week_metrics(data,pd.DataFrame(),pd.DataFrame())
assert r["graded_d1"]==2 and r["rejected_non_pretip"]==1
assert r["paired"]==1 and r["baseline_mae"]==4.5
assert r["paired_baseline_mae"]==3 and r["paired_roster_mae"]==1
assert opening_week_metrics(pd.DataFrame(),pd.DataFrame(),pd.DataFrame())["graded_d1"]==0
print("V135 tests passed")

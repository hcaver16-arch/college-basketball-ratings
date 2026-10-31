"""Synthetic V134 test for observed finals and bounded coverage classifications."""
import sys, types
import pandas as pd
st=types.ModuleType("streamlit")
st.cache_data=lambda **kwargs: lambda fn: fn
sys.modules["streamlit"]=st
from forecast_coverage_v134 import coverage_report

f=pd.DataFrame({"Game ID":["1","3"]})
e=pd.DataFrame({"Game ID":["1"]})
season=pd.DataFrame({"Game ID":["1","2","3","4"],"Status":["Final","Final","Final","Scheduled"]})
classes=pd.DataFrame({"Game ID":["1","2","3"],"Matchup class":["D1 vs D1","D1 vs D1","D1 vs D1"]})
status={"forecast_diagnostics":{"schedule_games":8,"future_scheduled_games":5,"previously_archived":3,"missing_rating":1,"baseline_eligible":1}}
r=coverage_report(f,e,season,classes,status)
assert r["observed_finals"]==3
assert r["finals_with_forecast"]==2
assert r["finals_without_forecast"]==1
assert r["known_d1_finals_without_forecast"]==1
assert r["forecasted_finals_awaiting_grading"]==1
assert r["latest_window"]["future_reconciled"]
assert coverage_report(f,e,pd.DataFrame(),classes,status)["observed_finals"]==0
print("V134 synthetic coverage tests passed")

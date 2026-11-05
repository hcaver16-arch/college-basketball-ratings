"""V230: deliberate D1 newcomer holds must reconcile with forecast generation."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pandas as pd

from prediction_archive import schedule_diagnostics, forecast_new_games

now = datetime(2026,11,5,13,tzinfo=timezone.utc)
future = (now+timedelta(hours=9)).isoformat()
def fixture(gid, home, away):
    return {"Game ID":gid,"Game start UTC":future,"Status":"Scheduled",
            "Home ID":home,"Away ID":away,
            "Home":f"Team {home}","Away":f"Team {away}","Venue":"Home"}
schedule=pd.DataFrame([
    fixture("newcomer","200","2697"),
    fixture("ordinary","200","201"),
    fixture("missing","200","999"),
    fixture("already","200","202"),
])
rated=pd.DataFrame({
    "Team ID":["200","201","202","2697"],
    "Current power":[7.0,3.5,-2.0,0.0],
    "As of UTC":[now.isoformat()]*4,
})
rosters=(pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),None)
with patch("prediction_archive.evidence_adjustments",return_value={}):
    counts=schedule_diagnostics(schedule,rated,rosters,now,{"already"})
    forecasts=forecast_new_games(schedule,rated,rosters,now,
                                 "womens-college-basketball",{"already"})
assert counts["future_scheduled_games"]==4,counts
assert counts["newcomer_hold"]==1,counts
assert counts["previously_archived"]==1,counts
assert counts["missing_rating"]==1,counts
assert counts["baseline_eligible"]==1,counts
assert counts["roster_eligible"]==0
assert len(forecasts)==counts["baseline_eligible"]==1
assert forecasts.iloc[0]["Game ID"]=="ordinary"
assert not forecasts["Game ID"].isin(["newcomer","already","missing"]).any()

# The read-only coverage audit must reconcile all outcomes.
import sys,types
st=types.ModuleType("streamlit")
st.cache_data=lambda **kw:lambda fn:fn
sys.modules["streamlit"]=st
from forecast_coverage_v134 import coverage_report
status={"forecast_diagnostics":counts}
empty=pd.DataFrame()
report=coverage_report(empty,empty,empty,empty,status)
window=report["latest_window"]
assert window["future_reconciled"],window
assert window["accounted_for_future"]==4
assert window["newcomer_hold"]==1
print("V230 separate newcomer holds and forecast coverage reconciliation passed")

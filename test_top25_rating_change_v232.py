"""V232 regression: rating change is versus preseason, not last snapshot."""
import numpy as np
import pandas as pd
from audit_top25_rating_change_v232 import audit_snapshot

ids={str(i) for i in range(1,300)}
rows=[]
for i in range(1,301):
    baseline=25.-i/10
    # Important: large baseline schools may all decline after season
    current=baseline-.9 if i<=25 else baseline+.5
    rows.append({"Team ID":str(i),"Team":f"Team {i}",
                 "Rank":i,"Current power":current,
                 "Preseason rating":baseline,
                 "On-court rating": 2. if i<=25 else -4.,
                 "Games played":1,"On-court weight":.07,
                 "Rating change":current-baseline})
latest=pd.DataFrame(rows)
history=[]
for day in ("2026-11-05","2026-11-06"):
    for r in rows:
        val=r["Current power"]-(.2 if day=="2026-11-05" else 0)
        history.append({"Team ID":r["Team ID"],"Snapshot date":day,
                        "Current power":val})
h=pd.DataFrame(history)
top,summary=audit_snapshot(latest,ids,h,season=None,size=25)
assert len(top)==25
assert summary["top25_below_preseason"]==25
assert summary["top25_above_preseason"]==0
assert summary["top25_increased_since_previous_snapshot"]==25
assert summary["top25_decreased_since_previous_snapshot"]==0
assert summary["top25_avg_vs_preseason"]==-.9
assert summary["previous_snapshot_date"]=="2026-11-05"
assert top.iloc[0]["Team"]=="Team 1"
assert np.isclose(top.iloc[0]["Change since previous snapshot"],.2)
assert summary["all_D1_rating_change_positive"]>0

# Never silently trust precomputed Rating change if stale or incorrectly keyed.
wrong=latest.copy()
wrong.loc[0,"Rating change"]=20.
try:
    audit_snapshot(wrong,ids,h,season=None,size=25)
    raise AssertionError("Should not trust false rating change")
except AssertionError:pass

# Drop unverified/nonD1 IDs even when their raw rating is high.
only={str(i) for i in range(2,300)}
top2,_=audit_snapshot(latest,only,h,season=None,size=25)
assert top2.iloc[0]["Team ID"]=="2"
assert "1" not in set(top2["Team ID"])
print("V232 top25 vs-preseason and prior-daily-snapshot separation passed")

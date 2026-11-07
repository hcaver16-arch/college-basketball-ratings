"""V233: truthful movement between *saved* dated power snapshots.

The column 'Rating change' already means current power minus preseason.
This helper computes a separate previous-archive-update difference using
real stored snapshots, never a same-game invented estimate.
"""
from __future__ import annotations
import pandas as pd

COLS=["Team ID","Previous snapshot date","Previous snapshot power","Since previous snapshot"]


def latest_movement(latest:pd.DataFrame,history:pd.DataFrame)->pd.DataFrame:
    empty=pd.DataFrame(columns=COLS)
    if not isinstance(latest,pd.DataFrame) or not isinstance(history,pd.DataFrame):
        return empty
    if latest.empty or history.empty:
        return empty
    if not {"Team ID","Current power"}.issubset(latest) or not {
        "Team ID","Snapshot date","Current power"}.issubset(history):
        return empty
    x=latest[["Team ID","Current power"]].copy()
    x["Team ID"]=x["Team ID"].astype(str)
    x["Current power"]=pd.to_numeric(x["Current power"],errors="coerce")
    h=history[["Team ID","Snapshot date","Current power"]].copy()
    h["Team ID"]=h["Team ID"].astype(str)
    h["Snapshot date"]=pd.to_datetime(h["Snapshot date"],errors="coerce",utc=True,format="mixed")
    h["Current power"]=pd.to_numeric(h["Current power"],errors="coerce")
    h=h.dropna(subset=["Snapshot date","Current power"])
    if h.empty:return empty
    days=sorted(h["Snapshot date"].dt.date.unique())
    if len(days)<2:return empty
    latest_day,previous_day=days[-1],days[-2]
    current_day=h[h["Snapshot date"].dt.date==latest_day]
    # Never present a prior day's change if latest.csv differs from the
    # newest persisted dated row (an incomplete refresh).
    current_day=current_day.drop_duplicates("Team ID",keep="last")
    existing=current_day.set_index("Team ID")["Current power"]
    prev=h[h["Snapshot date"].dt.date==previous_day].drop_duplicates("Team ID",keep="last")
    prior=prev.set_index("Team ID")["Current power"]
    x["Expected archived power"]=x["Team ID"].map(existing)
    x["Previous snapshot power"]=x["Team ID"].map(prior)
    ok=x["Expected archived power"].sub(x["Current power"]).abs().le(.025)
    x["Since previous snapshot"]=x["Current power"].sub(x["Previous snapshot power"]).where(ok)
    x["Previous snapshot power"]=x["Previous snapshot power"].where(ok)
    x["Previous snapshot date"]=str(previous_day)
    x.loc[~ok,"Previous snapshot date"]=pd.NA
    return x[COLS].drop_duplicates("Team ID")


def movement_for_team(history:pd.DataFrame)->tuple[float|None,str|None]:
    """Latest minus immediately prior saved day, no extrapolation."""
    if not isinstance(history,pd.DataFrame) or history.empty:
        return None,None
    if not {"Current power","Snapshot date"}.issubset(history):
        return None,None
    h=history.copy()
    h["Snapshot date"]=pd.to_datetime(h["Snapshot date"],errors="coerce",utc=True,format="mixed")
    h["Current power"]=pd.to_numeric(h["Current power"],errors="coerce")
    h=h.dropna(subset=["Snapshot date","Current power"]).sort_values("Snapshot date")
    h["Day"]=h["Snapshot date"].dt.date
    h=h.drop_duplicates("Day",keep="last")
    if len(h)<2:return None,None
    return float(h.iloc[-1]["Current power"]-h.iloc[-2]["Current power"]),str(h.iloc[-2]["Day"])

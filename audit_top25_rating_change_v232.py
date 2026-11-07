"""V232 read-only audit: are the top 25 systematically penalized by cold-start ridge?

Uses exactly the same saved team rating snapshots as the published Courtside app.
Separates *vs preseason* from *vs previous daily snapshot*. Checks D1 membership,
on-court shrinkage, and a strictly research-only preseason-anchored comparison.
No production ratings, forecasts or sources are modified.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
from prior_transition_research_v229 import anchored_ridge, normalize

DIVISIONS=("mens-college-basketball","womens-college-basketball")
FIELDS=["Team ID","Team","Rank","Current power","Preseason rating",
        "On-court rating","Games played","Rating change","On-court weight"]


def audit_snapshot(latest, ids, history=None, season=None, size=25):
    missing=set(FIELDS)-set(latest.columns)
    if missing:raise ValueError(f"Missing saved rating fields: {sorted(missing)}")
    frame=latest.copy()
    frame["Team ID"]=frame["Team ID"].astype(str)
    if frame["Team ID"].duplicated().any():raise ValueError("Duplicate rated teams")
    for field in FIELDS[2:]:
        frame[field]=pd.to_numeric(frame[field],errors="coerce")
    frame=frame[frame["Team ID"].isin(set(map(str,ids)))].dropna(
        subset=["Current power","Preseason rating","Rating change"]).copy()
    if len(frame)<min(200,size*5):raise ValueError("Too few rated D1 teams for top-25 integrity audit")
    frame=frame.sort_values("Current power",ascending=False)
    # The displayed rank comes from the full solved pool, including non-D1
    # schools; derive the actual D1 top-25 separately, exactly as the site does.
    top=frame.head(size).copy()
    for _,r in top.iterrows():
        assert abs((r["Current power"]-r["Preseason rating"])-r["Rating change"])<=0.025
    earliest=None
    if isinstance(history,pd.DataFrame) and not history.empty:
        h=history.copy()
        h["Team ID"]=h["Team ID"].astype(str)
        h["Snapshot date"]=h["Snapshot date"].astype(str)
        dates=sorted(h["Snapshot date"].dropna().unique().tolist())
        if len(dates)>=2:
            latest_day=dates[-1]
            old_day=dates[-2]
            old=h[h["Snapshot date"].eq(old_day)].set_index("Team ID")
            earlier=pd.to_numeric(old["Current power"],errors="coerce")
            top["Previous snapshot power"]=top["Team ID"].map(earlier)
            top["Previous snapshot date"]=old_day
            top["Change since previous snapshot"]=top["Current power"]-top["Previous snapshot power"]
            earliest=old_day
    top["D1 rank"]=range(1,len(top)+1)
    totals={
        "rated_d1_count":len(frame),
        "top_n":len(top),
        "top25_below_preseason":int(top["Rating change"].lt(-0.025).sum()),
        "top25_above_preseason":int(top["Rating change"].gt(0.025).sum()),
        "top25_unchanged_within_rounding":int(top["Rating change"].abs().le(0.025).sum()),
        "top25_avg_vs_preseason":round(float(top["Rating change"].mean()),3),
        "top25_median_vs_preseason":round(float(top["Rating change"].median()),3),
        "top25_median_preseason_strength":round(float(top["Preseason rating"].median()),3),
        "top25_median_oncourt_strength":round(float(top["On-court rating"].median()),3) if top["On-court rating"].notna().any() else None,
        "top25_games_played_min":int(top["Games played"].min()),
        "top25_games_played_max":int(top["Games played"].max()),
        "top25_with_zero_games":int(top["Games played"].eq(0).sum()),
        "top25_with_positive_games":int(top["Games played"].gt(0).sum()),
        "top25_median_oncourt_weight":round(float(top["On-court weight"].median()),4),
        "all_D1_rating_change_positive":int(frame["Rating change"].gt(0.025).sum()),
        "all_D1_rating_change_negative":int(frame["Rating change"].lt(-0.025).sum()),
        "previous_snapshot_date":earliest,
    }
    if "Change since previous snapshot" in top:
        d=top["Change since previous snapshot"].dropna()
        totals.update({
            "top25_compared_previous_snapshot":len(d),
            "top25_increased_since_previous_snapshot":int(d.gt(0.025).sum()),
            "top25_decreased_since_previous_snapshot":int(d.lt(-0.025).sum()),
            "top25_previous_snapshot_mean_delta":round(float(d.mean()),3) if len(d) else None,
        })
    top["Anchored strength"]=np.nan
    if season is not None and not season.empty:
        # The candidate is an AFTER-GAMES illustration using identical saved
        # games. It is not a prospective forecast or model-selection test.
        priors=dict(zip(frame["Team ID"],frame["Preseason rating"]))
        # Include every saved prior-rated opponent (including non-D1) in the
        # anchored fit, mirroring the official all-opponent game graph.
        allprior=latest.copy()
        allprior["Team ID"]=allprior["Team ID"].astype(str)
        allprior["Preseason rating"]=pd.to_numeric(allprior["Preseason rating"],errors="coerce")
        priors=dict(zip(allprior["Team ID"],allprior["Preseason rating"].fillna(0)))
        valid=normalize(season,"saved-current-season")
        alternative=anchored_ridge(priors,valid)
        top["Anchored strength"]=top["Team ID"].map(alternative)
        top["Anchored vs preseason"]=top["Anchored strength"]-top["Preseason rating"]
        totals.update({
            "research_only_anchored_top25_above_preseason":int(top["Anchored vs preseason"].gt(0.025).sum()),
            "research_only_anchored_top25_below_preseason":int(top["Anchored vs preseason"].lt(-0.025).sum()),
            "research_only_anchored_top25_avg_delta":round(float(top["Anchored vs preseason"].mean()),3),
            "current_season_finals_available":len(valid),
        })
    cols=["D1 rank","Team","Team ID","Games played","Preseason rating",
          "On-court rating","On-court weight","Current power","Rating change",
          "Previous snapshot power","Change since previous snapshot",
          "Anchored strength","Anchored vs preseason"]
    for c in cols:
        if c not in top:top[c]=np.nan
    return top[cols],totals


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("."))
    p.add_argument("--out",type=Path,default=Path("data/research_top25_v232"))
    args=p.parse_args()
    from reliability_v99 import fetch_d1_membership
    outputs={};reports={}
    for sport in DIVISIONS:
        base=args.root/"data"/"ratings"/sport
        latest=pd.read_csv(base/"latest.csv.gz",dtype={"Team ID":str})
        history=pd.read_csv(base/"history.csv.gz",dtype={"Team ID":str})
        season=pd.read_csv(base/"season_2026-27.csv.gz",
                           dtype={"Game ID":str,"Home ID":str,"Away ID":str})
        d1=fetch_d1_membership(sport)
        top,report=audit_snapshot(latest,d1,history,season)
        status=json.loads((base/"status.json").read_text())
        report["as_of_snapshot_date"]=status.get("snapshot_date")
        report["as_of_updated_utc"]=status.get("updated_utc")
        report["note"]="Last 25 sorted on published Current power, filtered to ESPN-verified current D1 membership. Change is vs preseason, not necessarily change since last game."
        reports[sport]=report
        outputs[sport]=top
    args.out.mkdir(parents=True,exist_ok=True)
    for sport,frame in outputs.items():
        frame.to_csv(args.out/f"{sport}_top25.csv",index=False)
    payload={
        "version":232,
        "run_at_utc":datetime.now(timezone.utc).isoformat(),
        "status":"RESEARCH_ONLY_NO_LIVE_RATINGS_CHANGED",
        "divisions":reports,
        "caveats":[
            "This audit describes saved ratings as of the indicated snapshot timestamp only.",
            "D1 top25 is sorted among currently verified D1 members; not an AP/Coaches top 25.",
            "The anchored alternative is a retrospective after-results illustration, not an independent forecast accuracy comparison.",
            "Do not promote a model based on its count of positive rating changes: calibrate on held-out pre-tip margin/winner accuracy.",
        ],
    }
    (args.out/"summary.json").write_text(json.dumps(payload,indent=2)+"\n")
    print("V232_SUMMARY_START")
    print(json.dumps(payload,indent=2))
    print("V232_SUMMARY_END")
    print("V232_TOP25_ROWS_START")
    for sport,frame in outputs.items():
        print("DIVISION",sport)
        for rec in frame.to_dict("records"):
            print(f"{int(rec['D1 rank']):02d} {rec['Team']}: "
                  f"games={rec['Games played']:.0f} pre={rec['Preseason rating']:+.2f} "
                  f"on_court={rec['On-court rating']:+.2f} "
                  f"power={rec['Current power']:+.2f} vs_pre={rec['Rating change']:+.2f} "
                  f"vs_prev_day={rec['Change since previous snapshot']:+.2f} "
                  f"anchored_research={rec['Anchored strength']:+.2f}")
    print("V232_TOP25_ROWS_END")

if __name__=="__main__":main()

"""V233: compare genuinely locked first-forecast *pairs*; no hindsight fits.

Consumes immutable V97 forecasts/results only, never rebuilds forecasts from
completed games. Paired accuracy is reported on the exact same fixtures, with
a conservative bound on the times the two models were first locked.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
from prospective_archive_v97 import FIELDS, RESULT_FIELDS, read_csv, parse_dt

OFFICIAL="official_saved_v97"
ANCHOR="experimental_anchored_ridge8_v233"
MAX_LOCK_GAP_HOURS=6
MIN_INFORMATIVE=100


def scored_pairs(forecasts:list[dict],results:list[dict],max_gap_hours=MAX_LOCK_GAP_HOURS):
    lookup={}
    for row in results:
        if row.get("status")!="Final":continue
        key=(row.get("division"),row.get("game_id"))
        if key in lookup:
            raise ValueError("Duplicate settled game in V97 source")
        lookup[key]=row
    slots={}
    for row in forecasts:
        model=row.get("model_id")
        if model not in (OFFICIAL,ANCHOR):
            continue
        key=(row.get("division"),row.get("game_id"),model)
        if key in slots:
            raise ValueError("Duplicate locked forecast ID: "+str(key))
        slots[key]=row
    out=[]
    paired=0
    excluded={"late_or_invalid_time":0,"different_lock_windows":0,
              "missing_valid_score":0,"bad_prediction":0}
    for division,gid,model in sorted(slots):
        if model!=OFFICIAL:continue
        other=slots.get((division,gid,ANCHOR))
        if other is None:continue
        baseline=slots[(division,gid,OFFICIAL)]
        paired+=1
        ta=parse_dt(baseline.get("forecast_created_utc"))
        tb=parse_dt(other.get("forecast_created_utc"))
        tip_a=parse_dt(baseline.get("game_start_utc"))
        tip_b=parse_dt(other.get("game_start_utc"))
        source_a=parse_dt(baseline.get("ratings_snapshot_utc"))
        source_b=parse_dt(other.get("ratings_snapshot_utc"))
        if not all((ta,tb,tip_a,tip_b,source_a,source_b)) or tip_a!=tip_b or not (source_a<=ta<tip_a and source_b<=tb<tip_a):
            excluded["late_or_invalid_time"]+=1;continue
        gap=abs((ta-tb).total_seconds())/3600.
        if gap>max_gap_hours:
            excluded["different_lock_windows"]+=1;continue
        score=lookup.get((division,gid))
        if score is None:
            continue # pending is not an excluded failure
        try:
            actual=float(score["actual_home_margin"])
            old=float(baseline["predicted_home_margin"])
            fresh=float(other["predicted_home_margin"])
        except (KeyError,TypeError,ValueError):
            excluded["bad_prediction"]+=1;continue
        if not all(np.isfinite(x) for x in (actual,old,fresh)):
            excluded["bad_prediction"]+=1;continue
        if str(baseline.get("home_id"))!=str(other.get("home_id")) or str(baseline.get("away_id"))!=str(other.get("away_id")):
            excluded["bad_prediction"]+=1;continue
        out.append({
            "division":division,"game_id":gid,
            "game_start_utc":baseline.get("game_start_utc"),
            "official_locked_utc":baseline.get("forecast_created_utc"),
            "anchored_locked_utc":other.get("forecast_created_utc"),
            "lock_gap_hours":round(gap,5),
            "actual_home_margin":actual,
            "official_margin":old,"anchored_margin":fresh,
            "official_abs_error":abs(actual-old),
            "anchored_abs_error":abs(actual-fresh),
            "informative":abs(old-fresh)>.05,
        })
    return pd.DataFrame(out,columns=[
        "division","game_id","game_start_utc","official_locked_utc",
        "anchored_locked_utc","lock_gap_hours","actual_home_margin",
        "official_margin","anchored_margin","official_abs_error",
        "anchored_abs_error","informative"]), {"paired_ever_locked":paired,**excluded}


def accuracy(df,key):
    if df.empty:
        return {"games":0,"mae":None,"rmse":None,"winner_accuracy":None,"bias":None}
    actual=df["actual_home_margin"].to_numpy(float)
    pred=df[key].to_numpy(float)
    err=actual-pred
    valid=(actual!=0)&(pred!=0)
    return {
        "games":len(df),
        "mae":round(float(np.mean(np.abs(err))),4),
        "rmse":round(float(np.sqrt(np.mean(err**2))),4),
        "winner_accuracy":round(float(np.mean(np.sign(actual[valid])==np.sign(pred[valid]))),4) if valid.any() else None,
        "bias":round(float(np.mean(err)),4),
    }


def report(forecasts,results):
    pairs,checks=scored_pairs(forecasts,results)
    detail={}
    for d in ("mens","womens"):
        dframe=pairs[pairs["division"].eq(d)]
        info=dframe[dframe["informative"]]
        detail[d]={
            "paired_graded_games":len(dframe),
            "informative_grades":len(info),
            "forecast_tolerance_for_information":0.05,
            "same_fixtures":True,
            "baseline":accuracy(dframe,"official_margin"),
            "anchored":accuracy(dframe,"anchored_margin"),
            "informative_only_baseline":accuracy(info,"official_margin"),
            "informative_only_anchored":accuracy(info,"anchored_margin"),
            "status":("NOT_ENOUGH_INFORMATIVE_GAMES_FOR_MODEL_SELECTION"
                      if len(info)<MIN_INFORMATIVE
                      else "RESEARCH_SAMPLE_REVIEW_REQUIRED"),
        }
        if not info.empty:
            detail[d]["informative_anchor_minus_baseline_mae"]=round(
                detail[d]["informative_only_anchored"]["mae"] -
                detail[d]["informative_only_baseline"]["mae"],4
            )
    return pairs,{
        "version":233,"generated_utc":datetime.now(timezone.utc).isoformat(),
        "status":"PROSPECTIVE_PAIRED_RESEARCH_ONLY",
        "model_ids":{"official":OFFICIAL,"anchored":ANCHOR},
        "max_lock_gap_hours":MAX_LOCK_GAP_HOURS,
        "lock_integrity_checks":checks,"divisions":detail,
        "limitations":[
            "Only immutable first forecasts made before tipoff; never backfilled.",
            "Both forecasts must exist for the same game and within six hours of each other.",
            "New candidate coverage starts when V233 is installed; earlier official-only games never receive reconstructed anchored predictions.",
            "Unplayed games are omitted until their final appears in V97's results archive.",
            "No model selection from win rate alone or from how many teams have positive rating changes.",
            "Preseason-anchored model is research only. The official ratings and first forecasts remain unmodified.",
        ],
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path("."))
    parser.add_argument("--season",default="2026-27")
    args=parser.parse_args()
    folder=args.root/"data"/"prospective"/args.season
    old=read_csv(folder/"forecasts.csv",FIELDS)
    results=read_csv(folder/"results.csv",RESULT_FIELDS)
    frames,info=report(old,results)
    frames.to_csv(folder/"anchored_pairs_v233.csv",index=False)
    (folder/"anchored_evaluation_v233.json").write_text(json.dumps(info,indent=2)+"\n")
    print(json.dumps(info,indent=2))


if __name__=="__main__":
    main()

"""V235: evaluate last-season-only preseason power against frozen roster evidence.

Research ONLY. No official ratings, V97 forecasts or 2026-27 fitted ratings
are modified. V105 source is an Oct 27 experimental hypothesis with unverified
ESPN roster memberships; that is NOT independently confirmed player impact.

Two distinct evaluations:
  retrospective: 2026-27 completed results with a frozen, before-season roster
  *descriptive* hypothesis (not a true historical forecast, no source time proof).
  track: append-only, genuinely locked NEW pre-tip pairs, scored only later.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import pandas as pd
import numpy as np

from rating_engine import calculate_power
from prior_transition_research_v229 import normalize
from prospective_archive_v97 import (
    scoreboard, parse_dt, iso, read_csv, write_csv, SPORTS,
)
from transition_research_v227 import newcomer_game

ROOT = Path(__file__).resolve().parent
MODEL_BASE = "v235_2025_26_preseason_only"
MODEL_ROSTER = "v235_v105_preseason_roster_assumption"
SOURCE_DIR = "data/roster_experiment_v105"
OUT_DIR = "data/preseason_research_v235"
MIN_PRIOR_GAMES = 1000
MIN_CONFIDENCE = .65
MIN_ROSTER_PLAYERS = 8
MIN_INFORMATIVE = 100
HCA = 3.
FORECAST_FIELDS = [
    "division","game_id","game_start_utc","home_id","away_id","home_team",
    "away_team","neutral","forecast_created_utc","roster_source_utc",
    "source_sha256","baseline_model_id","roster_model_id",
    "home_preseason_power","away_preseason_power",
    "home_roster_delta","away_roster_delta",
    "baseline_home_margin","roster_home_margin",
]
RESULT_FIELDS = [
    "division","game_id","game_start_utc","result_checked_utc",
    "home_score","away_score","actual_home_margin","status",
]


def digest(paths):
    h=hashlib.sha256()
    for path in paths:
        h.update(str(path.name).encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def flag(value):
    return str(value).strip().lower() in ("true","yes","1")


def build_preseason(root:Path, sport:str, now:datetime):
    """Verified historical team strengths plus conservatively gated V105 data."""
    if now.tzinfo is None: raise ValueError("As-of time must be UTC-aware")
    base=root/"data"/"ratings"/sport
    old_path=base/"history_2025-26.csv.gz"
    roster_path=root/SOURCE_DIR/f"{sport}_experimental_roster_sensitivity.csv"
    summary_path=root/SOURCE_DIR/"summary.json"
    if not all(p.is_file() for p in (old_path,roster_path,summary_path)):
        raise RuntimeError(f"{sport}: required frozen source not available")
    summary=json.loads(summary_path.read_text())
    source_time=parse_dt(summary.get("generated_at_utc"))
    # Source was assembled before this season started: never build the
    # candidate from a roster archive first created after tipoff.
    cutoff=datetime(2026,11,1,tzinfo=timezone.utc)
    if (summary.get("version")!=105 or source_time is None or
        not source_time<cutoff or not source_time<=now):
        raise RuntimeError(f"{sport}: source is not a genuinely pre-season V105 experiment")
    if summary.get("status")!="RESEARCH_ONLY_UNCALIBRATED_SENSITIVITY_NOT_A_PREDICTIVE_MODEL":
        raise RuntimeError(f"{sport}: V105 hypothesis status changed unexpectedly")
    old=pd.read_csv(old_path,dtype={"Game ID":str,"Home ID":str,"Away ID":str})
    prior,details=calculate_power(old)
    if prior.empty or details["games"]<MIN_PRIOR_GAMES:
        raise RuntimeError(f"{sport}: too few prior season final scores")
    if prior["Team ID"].astype(str).duplicated().any():
        raise RuntimeError("Duplicate historical rating IDs")
    roster=pd.read_csv(roster_path,dtype={"team_id":str})
    fields={
        "team_id","division","data_available","historical_boxscores_complete",
        "prior_roster_players","current_players","origin_coverage_fraction",
        "confidence_weight","illustrative_adjustment_points",
        "returning_minutes_pct_documented","incoming_prior_minutes_documented",
    }
    if not fields.issubset(roster):
        raise RuntimeError(f"{sport}: missing roster columns {fields-set(roster.columns)}")
    if roster["team_id"].isna().any() or roster["team_id"].duplicated().any() or not roster["division"].eq(sport).all():
        raise RuntimeError(f"{sport}: roster IDs/division mismatch")
    r=roster.copy()
    for c in ("prior_roster_players","current_players","origin_coverage_fraction",
              "confidence_weight","illustrative_adjustment_points",
              "returning_minutes_pct_documented","incoming_prior_minutes_documented"):
        r[c]=pd.to_numeric(r[c],errors="coerce")
    r["Qualified roster evidence"]=(
        r["data_available"].map(flag) &
        r["historical_boxscores_complete"].map(flag) &
        r["prior_roster_players"].ge(MIN_ROSTER_PLAYERS) &
        r["current_players"].ge(MIN_ROSTER_PLAYERS) &
        r["origin_coverage_fraction"].ge(MIN_CONFIDENCE) &
        r["confidence_weight"].ge(MIN_CONFIDENCE) &
        r["illustrative_adjustment_points"].notna() &
        r["illustrative_adjustment_points"].abs().le(2.0001) &
        r["returning_minutes_pct_documented"].between(0,100)
    )
    # Missing evidence is not zero talent or evidence of a negative roster.
    # For rankings, an unqualified team's scenario equals its baseline and
    # is explicitly flagged. Such teams never enter matched experiments.
    r["V235 roster adjustment"]=r["illustrative_adjustment_points"].where(
        r["Qualified roster evidence"]
    )
    prior=prior[["Team ID","Team","Power"]].copy()
    prior["Team ID"]=prior["Team ID"].astype(str)
    out=prior.rename(columns={"Power":"Baseline preseason power"})
    out=out.merge(r[[
        "team_id","Qualified roster evidence","V235 roster adjustment",
        "returning_minutes_pct_documented","incoming_prior_minutes_documented",
        "origin_coverage_fraction","confidence_weight",
    ]],left_on="Team ID",right_on="team_id",how="left",validate="one_to_one")
    out["Qualified roster evidence"]=out["Qualified roster evidence"].fillna(False).astype(bool)
    out["Roster scenario power"]=out["Baseline preseason power"]+out["V235 roster adjustment"].fillna(0.)
    out["Scenario adjustment status"]=np.where(
        out["Qualified roster evidence"],
        "V105_HEURISTIC_WITH_ESPN_ROSTER_EVIDENCE",
        "NO_QUALIFIED_EVIDENCE_BASELINE_HELD_UNCHANGED",
    )
    out=out.drop(columns=["team_id"]).sort_values("Baseline preseason power",ascending=False)
    return out, {
        "source_created_utc":iso(source_time),
        "source_sha256":digest((summary_path,roster_path,old_path)),
        "historical_games":int(details["games"]),
        "prior_rated_teams":len(out),
        "qualified_roster_teams":int(out["Qualified roster evidence"].sum()),
        "unqualified_roster_teams":int((~out["Qualified roster evidence"]).sum()),
        "method":"Frozen V105 illustrative (not fitted) roster adjustment; >=8 prior/current players, >=65% roster-origin coverage and confidence; previous 2025-26 game-margin prior.",
    }


def pairs_for_completed(season:pd.DataFrame, models:pd.DataFrame, ids:set[str]):
    """Retrospective explanation only; no previous score ever trains the priors."""
    valid=normalize(season,"V235 2026-27 completed games")
    rated=models.copy().set_index("Team ID")
    good=set(rated.loc[rated["Qualified roster evidence"]].index.astype(str))
    eligible=good & set(map(str,ids))
    frames=[]
    for g in valid.to_dict("records"):
        h,a=str(g["Home ID"]),str(g["Away ID"])
        if h not in eligible or a not in eligible:continue
        home=float(rated.at[h,"Baseline preseason power"])
        away=float(rated.at[a,"Baseline preseason power"])
        shift=float(rated.at[h,"V235 roster adjustment"])-float(rated.at[a,"V235 roster adjustment"])
        expected=home-away+(0 if g["Venue"]=="Neutral" else HCA)
        actual=float(g["Home score"])-float(g["Away score"])
        frames.append({
            "division":"","game_id":str(g["Game ID"]),"date":str(g["Date"]),
            "home_id":h,"away_id":a,"home_team":str(g["Home"]),"away_team":str(g["Away"]),
            "actual_home_margin":actual,
            "baseline_home_margin":expected,
            "roster_home_margin":expected+shift,
            "informative":abs(shift)>.05,
        })
    return pd.DataFrame(frames,columns=[
        "division","game_id","date","home_id","away_id","home_team","away_team",
        "actual_home_margin","baseline_home_margin","roster_home_margin","informative",
    ])


def metrics(df:pd.DataFrame, prediction:str):
    if df.empty:
        return {"games":0,"mae":None,"rmse":None,"winner_accuracy":None,"signed_bias":None}
    a=df["actual_home_margin"].to_numpy(float)
    p=df[prediction].to_numpy(float)
    if not (np.isfinite(a).all() and np.isfinite(p).all()):
        raise RuntimeError("Invalid score in research evaluation")
    e=a-p
    picks=(a!=0)&(p!=0)
    return {
        "games":len(df),
        "mae":round(float(abs(e).mean()),4),
        "rmse":round(float(np.sqrt(np.mean(e**2))),4),
        "winner_accuracy":round(float(np.mean(np.sign(a[picks])==np.sign(p[picks]))),4) if picks.any() else None,
        "signed_bias":round(float(np.mean(e)),4),
    }


def describe_matchups(df:pd.DataFrame):
    info=df.loc[df["informative"]] if not df.empty else df
    return {
        "matched_games":len(df),"informative_model_disagreement_games":len(info),
        "official_preseason_only":metrics(df,"baseline_home_margin"),
        "experimental_roster_preseason":metrics(df,"roster_home_margin"),
        "informative_only_baseline":metrics(info,"baseline_home_margin"),
        "informative_only_roster":metrics(info,"roster_home_margin"),
        "status":("EXPLORATORY_ONLY_EVIDENCE_INSUFFICIENT" if len(info)<MIN_INFORMATIVE
                  else "EXPLORATORY_MINIMUM_NOT_INDEPENDENT_VALIDATION"),
    }


def top_rankings(models:pd.DataFrame,ids:set[str]):
    d=models[models["Team ID"].isin(set(map(str,ids)))].copy()
    d["Preseason rank"]=d["Baseline preseason power"].rank(ascending=False,method="min")
    d["Roster scenario rank"]=d["Roster scenario power"].rank(ascending=False,method="min")
    d["Rank difference"]=d["Preseason rank"]-d["Roster scenario rank"]
    return d.sort_values("Baseline preseason power",ascending=False)


def future_candidates(now:datetime,games:dict,models:pd.DataFrame,division:str,
                      src:dict,existing:set[tuple[str,str]],ids:set[str]):
    if now.tzinfo is None: raise ValueError("Must timestamp the actual forecast")
    indexed=models.set_index("Team ID")
    allow=set(indexed.loc[indexed["Qualified roster evidence"]].index.astype(str))
    allow&=set(map(str,ids))
    out=[]
    for g in games.values():
        if g.get("final") or newcomer_game(g,season="2026-27"):continue
        gid=str(g.get("game_id") or "")
        h,a=str(g.get("home_id") or ""),str(g.get("away_id") or "")
        start=parse_dt(g.get("game_start_utc"))
        if (not gid or h==a or h not in allow or a not in allow or
            (division,gid) in existing or start is None or
            not now+timedelta(minutes=30)<start<=now+timedelta(hours=42)):
            continue
        home=float(indexed.at[h,"Baseline preseason power"])
        away=float(indexed.at[a,"Baseline preseason power"])
        hd=float(indexed.at[h,"V235 roster adjustment"])
        ad=float(indexed.at[a,"V235 roster adjustment"])
        neutral=bool(g.get("neutral"))
        baseline=home-away+(0 if neutral else HCA)
        out.append({
            "division":division,"game_id":gid,"game_start_utc":iso(start),
            "home_id":h,"away_id":a,"home_team":str(g.get("home_team","")),
            "away_team":str(g.get("away_team","")),"neutral":str(neutral).lower(),
            "forecast_created_utc":iso(now),"roster_source_utc":src["source_created_utc"],
            "source_sha256":src["source_sha256"],
            "baseline_model_id":MODEL_BASE,"roster_model_id":MODEL_ROSTER,
            "home_preseason_power":round(home,6),"away_preseason_power":round(away,6),
            "home_roster_delta":round(hd,6),"away_roster_delta":round(ad,6),
            "baseline_home_margin":round(baseline,6),
            "roster_home_margin":round(baseline+hd-ad,6),
        })
        existing.add((division,gid))
    return out


def graded_pairs(forecasts:list[dict],results:list[dict]):
    res={(x["division"],x["game_id"]):x for x in results if x.get("status")=="Final"}
    if len(res)!=len([x for x in results if x.get("status")=="Final"]):
        raise RuntimeError("Duplicate settled result keys")
    out=[]
    for f in forecasts:
        key=(f["division"],f["game_id"])
        r=res.get(key)
        if not r:continue
        created=parse_dt(f["forecast_created_utc"])
        tip=parse_dt(f["game_start_utc"])
        src=parse_dt(f["roster_source_utc"])
        if not all((created,tip,src)) or not src<=created<tip:
            raise RuntimeError("Research forecast appears after tipoff or source date")
        try:
            actual=float(r["actual_home_margin"])
            baseline=float(f["baseline_home_margin"])
            adjusted=float(f["roster_home_margin"])
        except (ValueError,TypeError):
            raise RuntimeError("Invalid archived forecast data")
        if not all(map(math.isfinite,(actual,baseline,adjusted))):
            raise RuntimeError("Non-finite archived values")
        out.append({
            "division":f["division"],"game_id":f["game_id"],
            "actual_home_margin":actual,
            "baseline_home_margin":baseline,
            "roster_home_margin":adjusted,
            "informative":abs(baseline-adjusted)>.05,
        })
    return pd.DataFrame(out,columns=[
        "division","game_id","actual_home_margin",
        "baseline_home_margin","roster_home_margin","informative",
    ])


def report_run(root:Path,out:Path,now:datetime,mode:str,scoreboard_reader=scoreboard,
               d1_reader=None):
    from reliability_v99 import fetch_d1_membership
    if d1_reader is None:d1_reader=fetch_d1_membership
    out.mkdir(parents=True,exist_ok=True)
    existing_forecasts=read_csv(out/"first_forecasts.csv",FORECAST_FIELDS) if mode=="track" else []
    existing_results=read_csv(out/"results.csv",RESULT_FIELDS) if mode=="track" else []
    if len({(f["division"],f["game_id"]) for f in existing_forecasts})!=len(existing_forecasts):
        raise RuntimeError("Duplicate historical first forecast: cannot append")
    if len({(r["division"],r["game_id"]) for r in existing_results})!=len(existing_results):
        raise RuntimeError("Duplicate historical settlement: cannot append")
    models_by_div={}
    evidence_by_div={}
    context={}
    new_forecasts=[]
    eligible={(f["division"],f["game_id"]) for f in existing_forecasts}
    score_updates=[]
    for sport in SPORTS:
        division="mens" if sport.startswith("mens-") else "womens"
        ids=set(map(str,d1_reader(sport)))
        if len(ids)<200:
            raise RuntimeError(f"{sport}: D1 membership lookup incomplete")
        model,source=build_preseason(root,sport,now)
        source["verified_d1_count"]=len(ids)
        ranked=top_rankings(model,ids)
        source["qualified_d1_team_count"]=int(ranked["Qualified roster evidence"].sum())
        models_by_div[division]=ranked
        evidence_by_div[division]=source
        # Model IDs must change if the frozen source is revised. Otherwise
        # a "same" model across games would have shifted coefficients.
        prior=[x for x in existing_forecasts if x["division"]==division]
        if prior and {x["source_sha256"] for x in prior}!={source["source_sha256"]}:
            raise RuntimeError(f"{division}: preseason input changed; require a new experimental version")
        if mode=="retrospective":
            season=pd.read_csv(root/"data"/"ratings"/sport/"season_2026-27.csv.gz",
                              dtype={"Home ID":str,"Away ID":str,"Game ID":str})
            paired=pairs_for_completed(season,model,ids)
            paired["division"]=division
            context[division]={"source":source,"sample":describe_matchups(paired),
                               "scope":"RETROSPECTIVE_RESULTS_ONLY_NOT_ACTUAL_LOCKED_FORECASTS"}
            paired.to_csv(out/f"{sport}_retrospective.csv",index=False)
        else:
            today=now.astimezone(__import__("zoneinfo").ZoneInfo("America/New_York")).date()
            games={}
            for offset in (-2,-1,0,1,2):
                games.update(scoreboard_reader(sport,today+timedelta(days=offset)))
            new_forecasts.extend(future_candidates(now,games,model,division,source,eligible,ids))
            # Grade only games that have already been properly first-forecast.
            all_eligible={(f["division"],f["game_id"]) for f in
                          existing_forecasts+new_forecasts}
            settled={(r["division"],r["game_id"]) for r in
                     existing_results+score_updates}
            for g in games.values():
                key=(division,str(g.get("game_id") or ""))
                if (key in settled or key not in all_eligible or not g.get("final")):
                    continue
                start=parse_dt(g.get("game_start_utc"))
                if not start or start>=now or g.get("home_score") is None or g.get("away_score") is None:
                    continue
                score_updates.append({
                    "division":division,"game_id":key[1],
                    "game_start_utc":iso(start),"result_checked_utc":iso(now),
                    "home_score":g["home_score"],"away_score":g["away_score"],
                    "actual_home_margin":int(g["home_score"])-int(g["away_score"]),
                    "status":"Final",
                })
            context[division]={"source":source,"new_pregame_pairs":len([
                f for f in new_forecasts if f["division"]==division
            ]),"scope":"IMMUTABLE_PROSPECTIVE_ONLY_NEW_GAMES"}

    if mode=="track":
        all_forecasts=existing_forecasts+new_forecasts
        all_results=existing_results+score_updates
        report_pairs=graded_pairs(all_forecasts,all_results)
        for d in ("mens","womens"):
            context[d]["prospective"]=describe_matchups(
                report_pairs[report_pairs["division"].eq(d)]
            )
            context[d]["locked_first_forecasts"]=len([
                f for f in all_forecasts if f["division"]==d
            ])
        # Only commit after both divisions and all source conditions passed.
        write_csv(out/"first_forecasts.csv",all_forecasts,FORECAST_FIELDS)
        write_csv(out/"results.csv",all_results,RESULT_FIELDS)
        report_pairs.to_csv(out/"graded_pairs.csv",index=False)
    for d,frame in models_by_div.items():
        frame.to_csv(out/f"{d}_rankings_research.csv",index=False)
    result={
        "version":235,"asof_utc":iso(now),"mode":mode,
        "status":"RESEARCH_ONLY_NOT_DEPLOYED",
        "divisions":context,
        "baseline_model_id":MODEL_BASE,
        "experimental_model_id":MODEL_ROSTER,
        "limits":[
            "V105 point impacts are UNTRAINED heuristic assumptions, not independently validated player values.",
            "ESPN roster snapshots from October 2026 may include identity ambiguities, unknown recruits, unsigned players and transfers; not independently verified enrollment.",
            "No roster adjustments without sufficient source and historical production coverage; unknown is NOT zero talent.",
            "Retrospective evaluation is exploratory and chosen after early 2026-27 results; it is NOT prospective evidence even though V105 was timestamped before Nov 1.",
            "Prospective first forecasts are locked before tipoff and never added after the fact.",
            "The roster model's first eligible future predictions begin only after this research workflow is installed.",
            "All scenarios share the SAME prior season scoring-margin model, isolating the incremental roster signal.",
            "Official basketball power ratings, other prospective archives, roster models, and public rankings remain unchanged.",
        ],
    }
    (out/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
    print("V235_REPORT_START")
    print(json.dumps(result,indent=2))
    print("V235_REPORT_END")
    return result


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,default=ROOT)
    ap.add_argument("--out",type=Path,default=ROOT/OUT_DIR)
    ap.add_argument("--mode",choices=("retrospective","track"),default="retrospective")
    args=ap.parse_args()
    report_run(args.root,args.out,datetime.now(timezone.utc),args.mode)

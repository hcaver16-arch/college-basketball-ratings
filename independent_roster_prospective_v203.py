#!/usr/bin/env python3
"""V203: isolated, prospective comparison of independently corroborated roster evidence.

Research ONLY: does not change live ratings, matchup spreads, or earlier pregame
predictions. Requires both teams to have sufficiently matched official-season
roster + ESPN game evidence and a freshly locked V97 baseline forecast.
The slope is a scenario assumption, not a fitted basketball model.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from prospective_roster_eval_v109 import FIELDS, rows, save, utc, number, evaluate

MODEL_ID = "v203_official_school_roster_research_v1"
SOURCE_FOLDER = Path("data/official_roster_evidence_v202")
PREV = "linked_players.csv"
CURR = "linked_current_players.csv"
SUMMARY = "summary.json"
SEASON = "2026-27"
SLOPE = 0.5  # 0.5 assumed margin points per 10 percentage points retained minutes
REFERENCE = 50.0
CAP = 3.0
REQUIRED_PRIOR_PLAYERS = 8
REQUIRED_STAT_COVERAGE = 0.90
REQUIRED_CURRENT_COVERAGE = 1.0  # fail closed on missing current season identities


def truth(x):
    return str(x).strip().lower() in ("true", "1", "yes")


def clean_ids(frame, tid):
    return frame.loc[frame["Team ID"].astype(str).eq(str(tid))].copy()


def load_evidence(root: Path, now: datetime, max_age_days: int = 240):
    """Read source-stamped, independently reconciled roster IDs and prior stats.

    A checked-at timestamp alone does NOT prove actual pregame membership. It
    merely gives a conservative earliest date on which this evidence is usable.
    """
    folder = root / SOURCE_FOLDER
    paths = [folder / name for name in (PREV, CURR, SUMMARY)]
    if not all(p.is_file() for p in paths):
        return None, "Official/ESPN reconciliation files missing"
    try:
        metadata = json.loads(paths[2].read_text())
        asof = utc(metadata.get("checked_utc"))
        if not asof or not timedelta(0) <= now - asof <= timedelta(days=max_age_days):
            return None, "Source verification timestamp unavailable, future, or stale"
        if metadata.get("division") != "mens-college-basketball" or metadata.get("model_changed") is not False:
            return None, "Source report is not a read-only men's independent audit"
        previous = pd.read_csv(paths[0], dtype={"Team ID":str,"ESPN Player ID":str}, keep_default_na=False)
        current = pd.read_csv(paths[1], dtype={"Team ID":str,"ESPN Player ID":str}, keep_default_na=False)
        stat_path = root / "data/mens-college-basketball_previous_stats.csv.gz"
        if not stat_path.is_file():
            return None, "Prior-year sourced ESPN stats unavailable"
        stats = pd.read_csv(stat_path, dtype={"Team ID":str,"Player ID":str})
        if not {"Team ID","Player ID","Minutes","Source","Game IDs","Games with box score"}.issubset(stats.columns):
            return None, "Player totals lack game-by-game provenance"
        required = {"Team ID","ESPN Player ID","Matched ESPN prior box scores",
                    "Matched ESPN current roster","Official source URL","Source checked UTC",
                    "Evidence classification"}
        if not required.issubset(previous.columns) or not required.issubset(current.columns):
            return None, "Incomplete linked roster evidence schema"
        for frame in (previous,current):
            if frame["Team ID"].astype(str).eq("").any():
                return None, "Malformed player IDs in roster source"
        # Evidence source fingerprint; future changes create a new provenance marker.
        digest = hashlib.sha256()
        for path in [*paths, stat_path]:
            digest.update(path.name.encode()); digest.update(path.read_bytes())
        return {"previous":previous, "current":current, "stats":stats,
                "created":asof, "sha":digest.hexdigest(), "source_files":[str(p.relative_to(root)) for p in [*paths,stat_path]]}, None
    except (OSError,ValueError,KeyError,TypeError,UnicodeError) as exc:
        return None, f"Could not validate independent roster source: {type(exc).__name__}: {exc}"


def candidates(snapshot):
    """Compute descriptive retention and qualification for any corroborated school."""
    old, current, totals = snapshot["previous"], snapshot["current"], snapshot["stats"]
    ids = sorted(set(old["Team ID"].astype(str)) | set(current["Team ID"].astype(str)))
    accepted, details = {}, {}
    for tid in ids:
        a, b, s = (clean_ids(frame,tid) for frame in (old,current,totals))
        why=[]
        if len(a) < REQUIRED_PRIOR_PLAYERS: why.append("fewer_than_8_official_prior_players")
        if b.empty: why.append("no_official_current_roster")
        if a["ESPN Player ID"].eq("").any() or a["ESPN Player ID"].duplicated().any():
            why.append("ambiguous_or_unlinked_prior_player")
        if b["ESPN Player ID"].eq("").any() or b["ESPN Player ID"].duplicated().any():
            why.append("ambiguous_or_unlinked_current_player")
        if not a.empty and (a["Official source URL"].eq("").any() or not a["Official source URL"].str.startswith("https://").all()):
            why.append("prior_official_source_missing")
        if not b.empty and (b["Official source URL"].eq("").any() or not b["Official source URL"].str.startswith("https://").all()):
            why.append("current_official_source_missing")
        old_ids = set(a["ESPN Player ID"].astype(str)) - {""}
        now_ids = set(b["ESPN Player ID"].astype(str)) - {""}
        # Reject the entire team when an official record has an ambiguous ID.
        qualified_old = set(a.loc[a["Matched ESPN prior box scores"].map(truth),"ESPN Player ID"]) & old_ids
        qualified_now = set(b.loc[b["Matched ESPN current roster"].map(truth),"ESPN Player ID"]) & now_ids
        stat_ids = set(s["Player ID"].dropna().astype(str))
        sourced = s[
            s["Player ID"].astype(str).isin(old_ids) &
            s["Source"].fillna("").astype(str).str.strip().ne("") &
            s["Game IDs"].fillna("").astype(str).str.strip().ne("")
        ].copy()
        sourced["Minutes"] = pd.to_numeric(sourced["Minutes"],errors="coerce")
        sourced["Games with box score"] = pd.to_numeric(sourced["Games with box score"],errors="coerce")
        sourced = sourced[
            sourced["Minutes"].notna() & sourced["Minutes"].ge(0) &
            sourced["Games with box score"].notna() & sourced["Games with box score"].gt(0)
        ]
        if sourced["Player ID"].duplicated().any(): why.append("duplicate_prior_player_stats")
        valid_ids = set(sourced["Player ID"].astype(str)) & qualified_old & stat_ids
        coverage = len(valid_ids)/len(a) if len(a) else 0.0
        current_coverage = len(qualified_now)/len(b) if len(b) else 0.0
        if coverage < REQUIRED_STAT_COVERAGE: why.append("prior_player_stats_below_90pct")
        if current_coverage < REQUIRED_CURRENT_COVERAGE: why.append("current_player_identity_not_all_correlated")
        usable = sourced[sourced["Player ID"].astype(str).isin(valid_ids)]
        total_minutes = float(usable["Minutes"].sum()) if not usable.empty else 0.0
        if not math.isfinite(total_minutes) or total_minutes <= 0:why.append("no_positive_source_minutes")
        returning_ids = now_ids & valid_ids
        returning_minutes = float(usable.loc[usable["Player ID"].astype(str).isin(returning_ids),"Minutes"].sum())
        retention = round(100.0 * returning_minutes/total_minutes,2) if total_minutes>0 else None
        record = {
            "team_id":tid, "official_prior_players":len(a), "official_current_players":len(b),
            "matched_prior_stats":len(valid_ids), "prior_stats_coverage_pct":round(coverage*100,1),
            "current_identity_coverage_pct":round(current_coverage*100,1),
            "returning_players_in_valid_stats":len(returning_ids), "retention_pct_known_only":retention,
            "blocked_reasons":sorted(set(why)), "qualified":not why,
        }
        if not why:
            delta = max(-CAP,min(CAP,(retention-REFERENCE)/10.0*SLOPE))
            record["hypothetical_adjustment_points"] = round(delta,3)
            accepted[tid] = round(delta,3)
        else:
            record["hypothetical_adjustment_points"] = None
        details[tid]=record
    return accepted,details


def lock_pairs(baselines, existing, adjustments, snapshot, now, season=SEASON,
               min_lead_minutes=30, max_baseline_age_minutes=60):
    """Only new locked V97 pregame baselines; never fill in a missed old event."""
    seen = {(r["division"],r["game_id"],r["model_id"]) for r in existing}
    created, skipped = [],Counter()
    for f in baselines:
        div = f.get("division")
        gid = str(f.get("game_id") or "")
        key = (div,gid,MODEL_ID)
        if div != "mens" or not gid or f.get("model_id") != "official_saved_v97" or key in seen:
            continue
        tip=utc(f.get("game_start_utc"))
        baseline_time=utc(f.get("forecast_created_utc"))
        rating_time=utc(f.get("ratings_snapshot_utc"))
        if not tip or not baseline_time or not rating_time or not (
            rating_time<=baseline_time<=now<tip-timedelta(minutes=min_lead_minutes)
            and snapshot["created"]<=baseline_time
        ):
            skipped["invalid_evidence_or_pregame_timing"]+=1
            continue
        if now-baseline_time>timedelta(minutes=max_baseline_age_minutes):
            skipped["baseline_prediction_not_fresh_no_backfill"]+=1
            continue
        home,away=str(f.get("home_id") or ""),str(f.get("away_id") or "")
        if home not in adjustments or away not in adjustments:
            skipped["one_or_both_teams_lack_verified_evidence"]+=1
            continue
        margin=number(f.get("predicted_home_margin"))
        if margin is None or home==away:
            skipped["invalid_baseline_margin"]+=1
            continue
        hdelta,adelta=adjustments[home],adjustments[away]
        created.append({
            "season":season, "division":"mens","game_id":gid,"game_start_utc":f["game_start_utc"],
            "home_id":home,"away_id":away,"home_team":f.get("home_team",""),
            "away_team":f.get("away_team",""),"neutral":f.get("neutral",""),
            "baseline_model_id":"official_saved_v97","baseline_forecast_created_utc":f["forecast_created_utc"],
            "paired_created_utc":now.isoformat().replace("+00:00","Z"),
            "ratings_snapshot_utc":f["ratings_snapshot_utc"],
            "baseline_snapshot_sha256":f.get("snapshot_sha256",""),
            "roster_snapshot_created_utc":snapshot["created"].isoformat().replace("+00:00","Z"),
            "roster_snapshot_sha256":snapshot["sha"],
            "baseline_predicted_home_margin":round(margin,6),
            "home_roster_adjustment":hdelta,"away_roster_adjustment":adelta,
            "experimental_predicted_home_margin":round(margin+hdelta-adelta,6),
            "model_id":MODEL_ID,
            "experiment_note":"Official school/ESPN-ID corroborated roster sensitivity; assumed coefficient, uncalibrated, not official odds",
        })
        seen.add(key)
    return created,dict(skipped)


def run(root:Path, now:datetime, season=SEASON,min_lead_minutes=30):
    if min_lead_minutes < 30:raise ValueError("Minimum pregame lead must be >=30 minutes")
    directory=root/"data"/"prospective"/season
    baseline_path=directory/"forecasts.csv"
    result_path=directory/"results.csv"
    pair_path=directory/"independent_roster_pairs_v203.csv"
    summary_path=directory/"independent_roster_evaluation_v203.json"
    baselines=rows(baseline_path)
    scores=rows(result_path)
    previous=rows(pair_path)
    if pair_path.exists():
        with pair_path.open(newline="",encoding="utf-8") as handle:
            cols=next(csv.reader(handle),[])
        if not set(FIELDS).issubset(cols): raise ValueError("Existing V203 pair journal has invalid schema; refusing overwrite")
    snapshot,error=load_evidence(root,now)
    signals,coverage=candidates(snapshot) if snapshot is not None else ({},{})
    additions,skip=lock_pairs(baselines,previous,signals,snapshot,now,season,min_lead_minutes) if snapshot else ([],{"source_unavailable":1})
    all_pairs=previous+additions
    # Immutable journal: append only. Existing rows are never recreated from updated evidence.
    if additions or not pair_path.exists():
        save(pair_path,all_pairs,FIELDS)
    result={
        "version":203,"season":season,"as_of_utc":now.isoformat().replace("+00:00","Z"),
        "status":"PROSPECTIVE_RESEARCH_ONLY_NOT_DEPLOYED",
        "production_model_modified":False,
        "published_pregame_forecasts_unchanged":True,
        "baseline_source":"immutable V97 official_saved_v97 forecasts",
        "source_errors":error,"source_checked_utc":snapshot["created"].isoformat().replace("+00:00","Z") if snapshot else None,
        "source_sha256":snapshot["sha"] if snapshot else None,
        "teams_audited":coverage,"qualified_team_count":len(signals),
        "new_pairs":len(additions),"total_pairs":len(all_pairs),
        "skipped":skip,
        "paired_results":evaluate(all_pairs,scores,min_lead_minutes),
        "limitations":[
            "Only baseline forecasts made after the official/ESPN evidence verification can be paired",
            "Both teams must have >=8 official previous-season players, >=90% valid prior-player totals and exact current IDs",
            "Observed school rosters are retrospective and do not establish any older pregame state",
            "Adjustment slope 0.5 pts per 10% returning minutes is untrained and must be evaluated before deployment",
            "No early-season or already completed game backfill; no replacement of first archived forecasts",
            "A zero returning estimate represents no matching sourced returnees, not known roster value",
            "No new live in-game win probabilities or betting odds are generated"
        ]
    }
    directory.mkdir(parents=True,exist_ok=True)
    summary_path.write_text(json.dumps(result,indent=2)+"\n")
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("."))
    p.add_argument("--season",default=SEASON)
    p.add_argument("--minimum-lead-minutes",type=int,default=30)
    args=p.parse_args()
    print(json.dumps(run(args.root,datetime.now(timezone.utc),args.season,args.minimum_lead_minutes),indent=2))

if __name__=="__main__":
    main()

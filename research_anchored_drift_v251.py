"""Courtside V251: research-only early-season rating drift and historical validation.

Retrospective 2024-25 D1-only frozen prior -> 2025-26 time-ordered
weekly holdouts. Compare the *structural* Courtside zero-centered
current-season ridge + game-count blend against fixed prior-anchored
ridge8 and ridge16, using identical fixtures. No training on holdout
games or chronological model selection. Separate descriptive analysis
of actual saved 2026-27 production snapshots is never mixed into
the historical holdout scores.

The historical baseline is a D1-only reconstruction of the production
math, NOT the exact original multi-division/non-D1 production archive.
Historical game venues are ESPN-derived and not independently verified.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from prior_transition_research_v229 import (
    legacy_replay, anchored_ridge,
)
from rating_engine import calculate_power
from research_preseason_scale_v240 import (
    normalize_paired, fit_frozen_prior, attach_saved_2025_26_venues,
    verify_collection_status,
)
from research_rating_updates_v247 import (
    ROOT, SPORTS, read, validate_snapshots,
)

METHODS = ("prior_only", "legacy_blended", "anchored_ridge8", "anchored_ridge16")
ORIGINS = tuple(date(2025, 11, 7)+timedelta(days=7*i) for i in range(15))
WINDOWS = tuple(zip(ORIGINS[:-1], ORIGINS[1:]))
MIN_EVALUATED_GAMES = 100


def to_engine(games: pd.DataFrame) -> pd.DataFrame:
    """Reuse V240's exactly game-ID/team/score-matched D1 fixture evidence."""
    needed = {"game_id", "day", "home_id", "away_id",
              "home_points", "away_points", "venue"}
    if missing := needed-set(games):
        raise ValueError(f"Missing historical joined columns: {sorted(missing)}")
    out = pd.DataFrame({
        "Game ID": games["game_id"].astype(str),
        "Date": games["day"].astype(str),
        "Home ID": games["home_id"].astype(str),
        "Away ID": games["away_id"].astype(str),
        "Home": games["home_id"].astype(str),
        "Away": games["away_id"].astype(str),
        "Home score": pd.to_numeric(games["home_points"], errors="raise"),
        "Away score": pd.to_numeric(games["away_points"], errors="raise"),
        "Venue": games["venue"],
        "Status": "Final",
    })
    out["day"] = pd.to_datetime(out["Date"], errors="raise").dt.date
    if out["Game ID"].duplicated().any():
        raise ValueError("Duplicate game IDs in matched historical data")
    if not out["Venue"].isin(["Home", "Neutral"]).all():
        raise ValueError("Invalid historical venue tag")
    if out["day"].isna().any():
        raise ValueError("Missing dated fixture")
    return out.sort_values(["day", "Game ID"]).reset_index(drop=True)


def number_played(train: pd.DataFrame) -> dict[str, int]:
    if train.empty:
        return {}
    return pd.concat((train["Home ID"], train["Away ID"])).value_counts().astype(int).to_dict()


def prediction(ratings: dict, row: dict) -> float:
    h, a = row["Home ID"], row["Away ID"]
    return (float(ratings[h])-float(ratings[a]) +
            (0. if row["Venue"] == "Neutral" else 3.))


def record_metrics(frame: pd.DataFrame, prediction_key: str) -> dict:
    if frame.empty:
        return {"games": 0, "mae": None, "bias": None,
                "winner_accuracy": None}
    actual = frame["actual_margin"].to_numpy(float)
    pred = frame[prediction_key].to_numpy(float)
    errors = actual-pred
    winner = (actual != 0) & (pred != 0)
    return {"games": len(frame),
            "mae": round(float(np.mean(np.abs(errors))), 5),
            "bias": round(float(np.mean(errors)), 5),
            "winner_accuracy": (
                round(float(np.mean(np.sign(actual[winner]) ==
                                    np.sign(pred[winner]))), 5)
                if winner.any() else None)}


def evaluate_windows(prior: dict[str, float], games: pd.DataFrame,
                     windows=WINDOWS):
    """Weekly contiguous holds, all fits use game days strictly before origin."""
    if not prior:
        raise ValueError("No frozen historical prior")
    prior = {str(k):float(v) for k,v in prior.items()}
    games = to_engine(games) if "day" not in games.columns else games.copy()
    all_rows, folds, drifts = [], [], []
    first_day = None
    for origin, stop in windows:
        if stop <= origin or (first_day is not None and origin < first_day):
            raise ValueError("Chronological windows overlap or are out of order")
        first_day = stop
        train = games[games["day"] < origin]
        held = games[(games["day"] >= origin) & (games["day"] < stop)]
        assert train.empty or max(train["day"]) < origin
        assert held.empty or min(held["day"]) >= origin
        legacy, _ = legacy_replay(prior, train)
        anchor8 = anchored_ridge(prior, train, ridge=8.)
        anchor16 = anchored_ridge(prior, train, ridge=16.)
        maps = {"prior_only": prior, "legacy_blended": legacy,
                "anchored_ridge8": anchor8, "anchored_ridge16": anchor16}
        counts = number_played(train)
        current_only, _ = calculate_power(train.drop(columns="day"))
        oncourt = dict(zip(current_only["Team ID"].astype(str),
                           current_only["Power"].astype(float)))
        covered = 0
        for game in held.to_dict("records"):
            home, away = str(game["Home ID"]), str(game["Away ID"])
            if home not in prior or away not in prior:
                continue
            row = {
                "game_id": game["Game ID"], "target_day": str(game["day"]),
                "window_start": str(origin), "window_stop_exclusive": str(stop),
                "last_training_day": str(max(train["day"])) if len(train) else "",
                "training_game_count": int(len(train)),
                "home_id": home, "away_id": away,
                "home_prior": float(prior[home]),
                "away_prior": float(prior[away]),
                "home_gp_before": int(counts.get(home, 0)),
                "away_gp_before": int(counts.get(away, 0)),
                "actual_margin": float(game["Home score"]-game["Away score"]),
                "venue": str(game["Venue"]),
            }
            for name, ratings in maps.items():
                row[name] = prediction(ratings, game)
            row["both_0_to_2_games"] = (
                row["home_gp_before"] <= 2 and row["away_gp_before"] <= 2)
            row["month"] = "November" if game["day"].month == 11 else (
                "December" if game["day"].month == 12 else "Jan/Feb")
            row["prior_stronger_team"] = (
                "home" if row["home_prior"] > row["away_prior"] else
                "away" if row["home_prior"] < row["away_prior"] else "tie")
            all_rows.append(row)
            covered += 1
        # Diagnostic cross-section at each forecast origin: no holdout used.
        quartile75 = float(np.quantile(list(prior.values()), 0.75))
        for tid, base in prior.items():
            gp = int(counts.get(tid, 0))
            if gp == 0:
                continue
            drifts.append({
                "origin": str(origin), "team_id": tid, "games_before": gp,
                "high_preseason_quartile": bool(base >= quartile75),
                "preseason_power": base,
                "current_only_power": float(oncourt[tid]) if tid in oncourt else np.nan,
                "legacy_blended_power": float(legacy[tid]),
                "anchored_ridge8_power": float(anchor8[tid]),
                "anchored_ridge16_power": float(anchor16[tid]),
                "legacy_drift": float(legacy[tid]-base),
                "anchored8_drift": float(anchor8[tid]-base),
                "anchored16_drift": float(anchor16[tid]-base),
                "current_only_minus_prior": float(oncourt[tid]-base)
                    if tid in oncourt else np.nan,
            })
        folds.append({
            "origin": str(origin), "stop_exclusive": str(stop),
            "training_game_count": len(train),
            "latest_used_training_day": str(max(train["day"])) if len(train) else None,
            "holdout_fixtures_in_source": len(held),
            "heldout_with_both_preseason_priors": covered,
        })
    result = pd.DataFrame(all_rows)
    drift = pd.DataFrame(drifts)
    if not result.empty and result["game_id"].duplicated().any():
        raise ValueError("Overlapping holdout game IDs")
    return result, drift, folds


def summarize_historical(preds: pd.DataFrame, drift: pd.DataFrame,
                         folds: list) -> dict:
    if len(preds) < MIN_EVALUATED_GAMES:
        raise ValueError(f"Insufficient historical holdout games: {len(preds)}")
    def scores(group):
        return {name: record_metrics(group, name) for name in METHODS}
    def delta(group):
        a = (group["actual_margin"]-group["anchored_ridge8"]).abs()
        b = (group["actual_margin"]-group["legacy_blended"]).abs()
        return {"games": len(group),
                "anchor8_minus_legacy_mae": round(float((a-b).mean()), 5),
                "anchor8_lower_absolute_error_games": int((a < b-1e-9).sum()),
                "legacy_lower_absolute_error_games": int((b < a-1e-9).sum()),
                "ties": int(np.isclose(a,b,atol=1e-9).sum())}
    cohort = []
    for label, group in (
        ("all", preds),
        ("both_0_to_2_prior_games", preds[preds["both_0_to_2_games"]]),
        ("either_3_plus_prior_games", preds[~preds["both_0_to_2_games"]]),
        ("November", preds[preds["month"]=="November"]),
        ("December", preds[preds["month"]=="December"]),
        ("January_and_February", preds[preds["month"]=="Jan/Feb"]),
        ("preseason_home_stronger", preds[preds["prior_stronger_team"]=="home"]),
        ("preseason_away_stronger", preds[preds["prior_stronger_team"]=="away"]),
    ):
        if len(group):
            cohort.append({"cohort": label, "paired_delta": delta(group),
                           "metrics": scores(group)})
    movement = []
    for (label, high), group in drift.groupby(
        [pd.cut(drift["games_before"], [0,2,5,1000], labels=["1-2","3-5","6+"]),
         "high_preseason_quartile"], observed=True):
        movement.append({
            "games_played_band": str(label),
            "strong_preseason_quartile": bool(high),
            "team_week_observations": len(group),
            "unique_teams": int(group["team_id"].nunique()),
            "mean_legacy_drift_from_prior": round(float(group["legacy_drift"].mean()), 5),
            "mean_anchored8_drift_from_prior": round(float(group["anchored8_drift"].mean()), 5),
            "mean_anchored16_drift_from_prior": round(float(group["anchored16_drift"].mean()), 5),
            "mean_current_only_minus_prior": (
                round(float(group["current_only_minus_prior"].mean()), 5)
                if group["current_only_minus_prior"].notna().any() else None),
            "legacy_fraction_dropped_below_prior": round(float(
                group["legacy_drift"].lt(-0.05).mean()), 5),
            "anchored8_fraction_dropped_below_prior": round(float(
                group["anchored8_drift"].lt(-0.05).mean()), 5),
        })
    return {
        "heldout_games": len(preds), "fixed_candidates": list(METHODS),
        "weekly_fold_metrics": [
            {"origin": f["origin"],
             "heldout_games": int((preds["window_start"] == f["origin"]).sum()),
             "scores": scores(preds[preds["window_start"] == f["origin"]])}
            for f in folds],
        "overall": scores(preds),
        "cohort_scores": cohort,
        "drift_crosstabs": movement,
        "fold_training_metadata": folds,
        "strict_earlier_dates_only": True,
        "candidates_selected_on_holdout": False,
    }


def actual_saved_season_drift(raw: pd.DataFrame) -> dict:
    """2026-27 production snapshots: one latest saved observation per team.

    Deliberately does not join 2025-26 historical scores or pretend to measure
    out-of-sample forecast quality.
    """
    snaps = validate_snapshots(raw)
    latest = snaps.sort_values("Snapshot date").groupby(
        "Team ID", sort=False).tail(1).copy()
    if latest.empty:
        return {"teams": 0, "cohorts": []}
    threshold = float(latest["Preseason rating"].quantile(0.75))
    latest["strong_prior_quartile"] = latest["Preseason rating"].ge(threshold)
    latest["drift"] = latest["Current power"]-latest["Preseason rating"]
    latest["band"] = pd.cut(latest["Games played"], [-1, 2, 5, 1000],
                            labels=["0-2", "3-5", "6+"])
    cohorts = []
    for (band, strong), group in latest.groupby(
            ["band", "strong_prior_quartile"], observed=True):
        cohorts.append({
            "games_played_band": str(band), "strong_prior_quartile": bool(strong),
            "teams": len(group),
            "mean_drift_from_preseason": round(float(group["drift"].mean()), 5),
            "fraction_below_preseason_0p05": round(float(
                group["drift"].lt(-0.05).mean()), 5),
            "mean_preseason_weight": round(float(
                group["Preseason weight"].mean()), 5)})
    return {"teams": len(latest),
            "latest_snapshot_day": str(max(latest["Snapshot date"])),
            "strong_quartile_threshold": round(threshold, 5),
            "cohorts": cohorts, "d1_only": False,
            "method": "one latest observed saved production snapshot per team"}


def load_historical(root: Path, division: str):
    suffix = "mens" if division.startswith("mens") else "womens"
    prior_path = root/"data/historical_efficiency"/f"2024-25_{suffix}_paired_games.csv.gz"
    test_path = root/"data/historical_efficiency"/f"2025-26_{suffix}_paired_games.csv.gz"
    scored_path = root/"data/ratings"/division/"history_2025-26.csv.gz"
    statuses = []
    paths = [prior_path, test_path, scored_path]
    for season in ("2024-25", "2025-26"):
        p = root/"data/historical_efficiency"/f"{season}_{suffix}_collection_status.json"
        if not p.is_file():
            raise FileNotFoundError(p)
        statuses.append(verify_collection_status(
            json.loads(p.read_text()), season, division))
        paths.append(p)
    if any(not p.is_file() for p in paths):
        raise FileNotFoundError(f"V251 missing historical inputs for {division}")
    previous = normalize_paired(pd.read_csv(prior_path,
        dtype={"game_id":str,"home_id":str,"away_id":str}), "2024-25")
    season = normalize_paired(pd.read_csv(test_path,
        dtype={"game_id":str,"home_id":str,"away_id":str}), "2025-26")
    archive = pd.read_csv(scored_path,
        dtype={"Game ID":str,"Home ID":str,"Away ID":str})
    matched, join_stats = attach_saved_2025_26_venues(season, archive)
    prior = fit_frozen_prior(previous)
    engine = to_engine(matched)
    metadata = {
        "paired_prior_games": len(previous), "matched_season_games": len(engine),
        "frozen_prior_teams": len(prior),
        "source_ledger_checks": statuses, "score_venue_crosswalk": join_stats,
        "source_sha256": {str(p.relative_to(root)):hashlib.sha256(
            p.read_bytes()).hexdigest() for p in paths}}
    return prior, engine, metadata


def run(root: Path, output: Path):
    root = root.resolve()
    output = output.resolve()
    if output == root or (root in output.parents and
                          not str(output).startswith(str(root/"data/research_v251"))):
        raise ValueError("Research outputs must be outside repo or in data/research_v251*")
    output.mkdir(parents=True, exist_ok=True)
    report = {"version": 251, "status": "RESEARCH_ONLY_NOT_DEPLOYED",
              "production_changed": False, "divisions": {},
              "historical_period": "2024-25 frozen D1 prior -> 2025-26 weekly retrospective holdouts",
              "historical_design": "fixed variants, before-origin training only, same test games",
              "assumptions_and_limitations": [
                  "Historical 2024-25 paired D1 dataset lacks independently verified neutral-site flags. Treats all prior games as designated home +3.",
                  "2025-26 ESPN Home/Neutral flags are crosswalked by exact game ID, team IDs and scores, not independently verified.",
                  "D1-only historical replay approximates production math but not the production multi-opponent graph, roster, or live archive.",
                  "Weekly historical holdouts are predicted at window open, not refreshed after games within a week; all candidates share same timeline.",
                  "Historical 2025-26 is a RETROSPECTIVE time-ordered reconstruction, not immutable archived real-time forecasts.",
                  "Anchored ridge strengths and home advantage are fixed, not optimized against tested games.",
                  "Team-week drift cross-tabs repeat a team across training dates; do not treat rows as independent.",
                  "2026-27 saved production-snapshot cohorts are descriptive only, include non-D1 teams and cannot validate historical model predictions.",
                  "No model promotion without additional independent evidence and the planned January checkpoint.",
              ]}
    for division in SPORTS:
        prior, historical, metadata = load_historical(root, division)
        predicted, drift, folds = evaluate_windows(prior, historical)
        summary = summarize_historical(predicted, drift, folds)
        actual = actual_saved_season_drift(read(
            root/"data/ratings"/division/"history.csv.gz"))
        report["divisions"][division] = {
            "historical_sources": metadata, "historical_holdout": summary,
            "actual_2026_27_production_snapshot_cohorts": actual}
        tag = "mens" if division.startswith("mens") else "womens"
        predicted.to_csv(output/f"{tag}_historical_weekly_forecasts.csv", index=False)
        drift.to_csv(output/f"{tag}_historical_rating_drift.csv", index=False)
    (output/"summary.json").write_text(json.dumps(
        report, indent=2, allow_nan=False)+"\n")
    print(json.dumps(report, indent=2, allow_nan=False))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=ROOT/"data/research_v251")
    a = parser.parse_args()
    run(a.root, a.out)

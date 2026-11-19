"""V252: immutable FIRST pre-tip shadow forecasts; never modify site ratings.

This runs after a successful daily ratings+official first-forecast refresh.
Pair ONLY brand-new official first forecasts with *the identical saved rating
snapshot* and the final-game archive available at capture. Later invocations
may evaluate the fixed predictions, but cannot backfill shadow forecasts for
previously locked games or change any existing shadow prediction value.

First pre-tip UTC timestamps and input hashes are stored per record. Scores
are refreshed in a separate evaluation file and may change after corrections.
No parameter fitting on evaluated outcomes, no retroactive predictions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from prediction_archive import read_gz, save_gz, as_utc
from prior_transition_research_v229 import anchored_ridge

ROOT = Path(__file__).resolve().parent
SPORTS = ("mens-college-basketball", "womens-college-basketball")
MAX_CAPTURE_LAG = timedelta(hours=3)
SNAPSHOT_GRACE = timedelta(minutes=5)
METHODS = ("Baseline home margin", "Prior-only home margin",
           "Anchored ridge8 home margin", "Anchored ridge16 home margin")
FIELDS = [
    "Division", "Game ID", "Home ID", "Away ID", "Home", "Away",
    "Venue", "Matchup class", "Game start UTC", "Baseline first forecast UTC",
    "Shadow first forecast UTC", "Rating snapshot UTC", "Days to tip at capture",
    "Baseline home margin", "Prior-only home margin",
    "Anchored ridge8 home margin", "Anchored ridge16 home margin",
    "Home prior", "Away prior", "Home games at capture",
    "Away games at capture", "Source rating SHA256", "Source final archive SHA256",
    "Model version", "Prospective evidence"
]


def timestamp(value):
    out = as_utc(value)
    if out is None:
        raise ValueError(f"Missing or invalid UTC timestamp: {value!r}")
    return out


def unique(frame, key, label):
    if not frame.empty and frame[key].astype(str).duplicated().any():
        raise ValueError(f"{label}: duplicated {key}; refusing to replace locked forecasts")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def final_training_games(raw: pd.DataFrame) -> pd.DataFrame:
    """Mirror scoring-margin production's valid-final game eligibility."""
    require = {"Game ID", "Home ID", "Away ID", "Home score",
               "Away score", "Venue", "Status"}
    if missing := require-set(raw):
        raise ValueError(f"Missing current final-game columns: {sorted(missing)}")
    d = raw.copy()
    d = d[d["Status"].eq("Final")].copy()
    for c in ("Home ID", "Away ID", "Game ID"):
        d[c] = d[c].astype("string").str.strip()
    d["Home score"] = pd.to_numeric(d["Home score"], errors="coerce")
    d["Away score"] = pd.to_numeric(d["Away score"], errors="coerce")
    d = d.dropna(subset=["Home ID", "Away ID", "Game ID",
                         "Home score", "Away score"])
    d = d[(d["Home ID"] != "") & (d["Away ID"] != "") &
          (d["Home ID"] != d["Away ID"])]
    for c in ("Home ID", "Away ID"):
        d = d[~d[c].str.lower().isin(("nan", "none", "<na>"))]
    d = d[d["Venue"].isin(("Home", "Neutral"))].copy()
    return d.drop_duplicates("Game ID", keep="first").reset_index(drop=True)


def candidate_rows(first: pd.DataFrame, existing: pd.DataFrame,
                   latest: pd.DataFrame, finals: pd.DataFrame,
                   classes: pd.DataFrame, now: datetime, sport: str,
                   rating_sha: str, final_sha: str):
    """Choose fair first-forecast pairs, strictly before the stored tip time.

    An unchanged baseline forecast is taken from the official first_forecasts
    file; never reconstruct that baseline at a later time.
    """
    unique(first, "Game ID", "official first forecast archive")
    unique(existing, "Game ID", "shadow forecast archive")
    unique(classes, "Game ID", "matchup classification")
    if latest.empty or "As of UTC" not in latest:
        raise ValueError("Missing saved rating snapshot timestamp")
    snapshot_values = latest["As of UTC"].dropna().astype(str).unique()
    if len(snapshot_values) != 1:
        raise ValueError("Ratings rows do not share one source timestamp")
    snapshot = timestamp(snapshot_values[0])
    if snapshot > now+SNAPSHOT_GRACE:
        raise ValueError("Rating source timestamp is in the future")
    if latest["Team ID"].astype(str).duplicated().any():
        raise ValueError("Duplicate latest rating team IDs")

    rated = latest.copy()
    rated["Team ID"] = rated["Team ID"].astype(str)
    for col in ("Current power", "Preseason rating", "Games played"):
        rated[col] = pd.to_numeric(rated[col], errors="coerce")
    if rated[["Current power", "Preseason rating", "Games played"]].isna().any().any():
        raise ValueError("Invalid rating input to shadow forecast")
    powers = rated.set_index("Team ID")["Current power"].to_dict()
    priors = rated.set_index("Team ID")["Preseason rating"].to_dict()
    games_at_capture = rated.set_index("Team ID")["Games played"].to_dict()
    classes_map = (classes.set_index("Game ID")["Matchup class"].to_dict()
                   if len(classes) else {})

    candidates = []
    locked = set(existing["Game ID"].astype(str))
    skipped = {"already_shadow_locked": 0, "official_lock_too_old": 0,
               "not_pre_tip": 0, "rating_snapshot_mismatch": 0,
               "unrated_matchup": 0, "invalid_official_forecast": 0}
    if now-snapshot > MAX_CAPTURE_LAG:
        # Never silently use an old snapshot to construct 'new' forecasts.
        return pd.DataFrame(columns=FIELDS), {
            **skipped, "stale_rating_snapshot": True,
            "fresh_eligible_official_locks": 0,
            "captured": 0}

    for g in first.to_dict("records"):
        gid = str(g["Game ID"])
        if gid in locked:
            skipped["already_shadow_locked"] += 1
            continue
        start = as_utc(g.get("Game start UTC"))
        official_first = as_utc(g.get("First forecast UTC"))
        if start is None or official_first is None or not (
                official_first < start and now < start):
            skipped["not_pre_tip"] += 1
            continue
        if not (snapshot-SNAPSHOT_GRACE <= official_first <= now and
                now-official_first <= MAX_CAPTURE_LAG):
            skipped["official_lock_too_old"] += 1
            continue
        if str(g.get("Rating snapshot date", "")) != snapshot_values[0]:
            skipped["rating_snapshot_mismatch"] += 1
            continue
        h, a = str(g["Home ID"]), str(g["Away ID"])
        if h not in powers or a not in powers:
            skipped["unrated_matchup"] += 1
            continue
        baseline = pd.to_numeric(g["Baseline home margin"], errors="coerce")
        if pd.isna(baseline):
            skipped["invalid_official_forecast"] += 1
            continue
        adv = 0. if g["Venue"] == "Neutral" else 3.
        if g["Venue"] not in ("Neutral", "Home"):
            skipped["invalid_official_forecast"] += 1
            continue
        if abs(float(baseline)-round(float(powers[h]-powers[a]+adv),2)) > 0.051:
            # The locked baseline must genuinely be from this saved rating
            # snapshot, or it cannot provide an equal-timestamp comparison.
            skipped["rating_snapshot_mismatch"] += 1
            continue
        candidates.append((g, h, a, start, official_first, float(baseline)))
    if not candidates:
        return pd.DataFrame(columns=FIELDS), {
            **skipped, "stale_rating_snapshot": False,
            "fresh_eligible_official_locks": 0, "captured": 0}

    # Fit only if we can capture newly locked first forecasts. All inputs
    # are already saved from a completed ratings refresh before this run.
    train = final_training_games(finals)
    anchored8 = anchored_ridge(priors, train, ridge=8.)
    anchored16 = anchored_ridge(priors, train, ridge=16.)
    rows = []
    for g, h, a, start, official_first, baseline in candidates:
        adv = 0. if g["Venue"] == "Neutral" else 3.
        rows.append({
            "Division": sport, "Game ID": str(g["Game ID"]),
            "Home ID": h, "Away ID": a,
            "Home": str(g["Home"]), "Away": str(g["Away"]),
            "Venue": g["Venue"],
            "Matchup class": classes_map.get(str(g["Game ID"]), "Unknown"),
            "Game start UTC": start.isoformat(),
            "Baseline first forecast UTC": official_first.isoformat(),
            "Shadow first forecast UTC": now.isoformat(),
            "Rating snapshot UTC": snapshot.isoformat(),
            "Days to tip at capture": round((start-now).total_seconds()/86400., 4),
            "Baseline home margin": baseline,
            "Prior-only home margin": round(float(priors[h]-priors[a]+adv), 4),
            "Anchored ridge8 home margin": round(
                float(anchored8[h]-anchored8[a]+adv), 4),
            "Anchored ridge16 home margin": round(
                float(anchored16[h]-anchored16[a]+adv), 4),
            "Home prior": float(priors[h]), "Away prior": float(priors[a]),
            "Home games at capture": int(games_at_capture[h]),
            "Away games at capture": int(games_at_capture[a]),
            "Source rating SHA256": rating_sha,
            "Source final archive SHA256": final_sha,
            "Model version": "V252 fixed priors, anchored ridge8/16, cap40, HCA3",
            "Prospective evidence": "FIRST_PRE_TIP_SHADOW_CAPTURED_WITH_FRESH_OFFICIAL_BASELINE"
        })
    return pd.DataFrame(rows, columns=FIELDS), {
        **skipped, "stale_rating_snapshot": False,
        "fresh_eligible_official_locks": len(candidates),
        "captured": len(rows)}


def append_first(existing: pd.DataFrame, newer: pd.DataFrame):
    unique(existing, "Game ID", "saved shadow")
    unique(newer, "Game ID", "new shadow")
    overlap = set(existing["Game ID"].astype(str)) & set(newer["Game ID"].astype(str))
    if overlap:
        raise ValueError(f"Would overwrite {len(overlap)} immutable first shadow predictions")
    return pd.concat([existing[FIELDS], newer[FIELDS]], ignore_index=True)


def evaluate(shadows: pd.DataFrame, finals: pd.DataFrame):
    """Refresh scores only; locked forecast values remain in separate file."""
    if shadows.empty:
        return pd.DataFrame()
    unique(shadows, "Game ID", "saved shadow")
    eligible = shadows.copy()
    for field in METHODS:
        eligible[field] = pd.to_numeric(eligible[field], errors="coerce")
    if eligible[list(METHODS)].isna().any().any():
        raise ValueError("Invalid immutable shadow prediction")
    valid = []
    for p in eligible.to_dict("records"):
        start = timestamp(p["Game start UTC"])
        base = timestamp(p["Baseline first forecast UTC"])
        shadow = timestamp(p["Shadow first forecast UTC"])
        snap = timestamp(p["Rating snapshot UTC"])
        if not (snap <= base <= shadow < start):
            raise ValueError("Archived shadow prediction violated pre-tip/source chronology")
        valid.append(p)
    eligible = pd.DataFrame(valid)
    scores = final_training_games(finals)
    joined = eligible.merge(
        scores[["Game ID", "Home ID", "Away ID", "Home score",
                "Away score"]], on="Game ID", how="inner", suffixes=("","_score"),
        validate="one_to_one")
    if joined.empty:
        return joined
    matching = (joined["Home ID"].astype(str) == joined["Home ID_score"].astype(str)) & (
        joined["Away ID"].astype(str) == joined["Away ID_score"].astype(str))
    joined = joined.loc[matching].copy()
    joined["Actual home margin"] = joined["Home score"]-joined["Away score"]
    for method in METHODS:
        joined[method+" absolute error"] = (
            joined["Actual home margin"]-joined[method]).abs()
    return joined


def metrics(evaluated: pd.DataFrame):
    def scores(data, method):
        if data.empty:
            return {"games": 0, "mae": None, "signed_bias": None,
                    "winner_accuracy": None}
        true = data["Actual home margin"].to_numpy(float)
        estimated = data[method].to_numpy(float)
        signed = true-estimated
        mask = (true != 0) & (estimated != 0)
        return {
            "games": len(data),
            "mae": round(float(np.abs(signed).mean()), 5),
            "signed_bias": round(float(signed.mean()), 5),
            "winner_accuracy": round(float((
                np.sign(true[mask]) == np.sign(estimated[mask])).mean()), 5)
            if mask.any() else None}
    def set_stats(data):
        scored = {method:scores(data,method) for method in METHODS}
        if len(data):
            for candidate in METHODS[1:]:
                a = data[candidate+" absolute error"].to_numpy(float)
                b = data["Baseline home margin absolute error"].to_numpy(float)
                scored[candidate]["mae_delta_vs_baseline"] = round(
                    float((a-b).mean()), 5)
                scored[candidate]["candidate_better_games"] = int((a<b-1e-9).sum())
                scored[candidate]["baseline_better_games"] = int((b<a-1e-9).sum())
        return {"paired_games": len(data), "models": scored}
    d1 = (evaluated[evaluated["Matchup class"].eq("D1 vs D1")]
          if len(evaluated) else evaluated)
    early = (d1[(d1["Home games at capture"].le(2)) &
                (d1["Away games at capture"].le(2))]
             if len(d1) else d1)
    return {
        "all_eligible_games": set_stats(evaluated),
        "d1_vs_d1_primary": set_stats(d1),
        "d1_both_0_to_2_previous_games": set_stats(early),
        "not_enough_games_to_select_model": len(d1) < 100,
        "no_production_model_changed": True,
        "interpretation": "Paired, first-pretip archived prospective forecasts; source schedule kickoff timestamps not independently audited for later rescheduling. Candidate rankings not deployed."}


def check_archive_status(status_path: Path, locked_path: Path):
    """A status from a zero-capture day must not block later first captures.

    Conversely, if we ever reported positive locked forecast counts, a
    missing archive is an integrity problem and must never be regenerated.
    """
    if not status_path.is_file() or locked_path.is_file():
        return
    state = json.loads(status_path.read_text())
    if type(state.get("locked_first_shadow_forecasts")) is not int or (
            state["locked_first_shadow_forecasts"] != 0):
        raise ValueError(
            "Shadow status reports locked forecasts but immutable archive is missing")


def prepare(root: Path, sport: str, now: datetime):
    base = root/"data"
    rating_path = base/"ratings"/sport/"latest.csv.gz"
    final_path = base/"ratings"/sport/"season_2026-27.csv.gz"
    official_path = base/"predictions"/sport/"first_forecasts.csv.gz"
    class_path = base/"predictions"/sport/"game_classification.csv.gz"
    output = base/"shadow_v252"/sport
    locked_path = output/"first_shadow_forecasts.csv.gz"
    status_path = output/"status.json"
    check_archive_status(status_path, locked_path)
    for path in (rating_path, final_path, official_path, class_path):
        if not path.is_file():
            raise FileNotFoundError(f"Missing official archival input: {path}")
    rated = read_gz(rating_path)
    finals = read_gz(final_path)
    official = read_gz(official_path)
    classes = read_gz(class_path)
    shadows = read_gz(locked_path, FIELDS)
    if list(shadows.columns) != FIELDS:
        raise ValueError("Unexpected locked shadow file schema; refuse overwrite")
    new, reasons = candidate_rows(
        official, shadows, rated, finals, classes, now, sport,
        sha(rating_path), sha(final_path))
    all_shadows = append_first(shadows, new)
    evaluated = evaluate(all_shadows, finals)
    report = {
        "version": 252, "division": sport,
        "updated_utc": now.isoformat(),
        "status": "RESEARCH_ONLY_NOT_DEPLOYED",
        "locked_first_shadow_forecasts": len(all_shadows),
        "new_pre_tip_shadow_forecasts": len(new),
        "new_capture_diagnostics": reasons,
        "evaluated_games": len(evaluated),
        "primary_d1_evaluated_games": int(
            evaluated["Matchup class"].eq("D1 vs D1").sum())
            if len(evaluated) else 0,
        "research_accuracy": metrics(evaluated),
        "safety_notes": [
            "No previously locked shadow forecast is changed or backfilled.",
            "Only new official first forecasts captured within three hours of the same saved rating snapshot are paired.",
            "Shadow timestamp is recorded at execution before archived game tip time; no old games or forecasts are retrospectively backfilled.",
            "The archive uses saved completed scores as of the latest refresh; source SHA256 permits identifying exactly which saved input files were used.",
            "Evaluation results may change if ESPN corrects a score, but first-shadow forecasts remain immutable.",
            "D1 labels are captured from the official classification file at first shadow lock; non-D1 matchups excluded from primary evaluation.",
            "Fixed candidate specifications were set before any V252 holdout game finished; no live ratings or UI is modified.",
            "Baseline and shadow timestamps can differ by up to three hours; do not call the outcomes perfectly simultaneous.",
            "No forecast used for betting advice or automatic production promotion."
        ]}
    return {"output": output, "locked_path": locked_path,
            "shadows": all_shadows, "evaluated": evaluated,
            "report": report, "write_first": len(new)>0}


def persist(prepared):
    p = prepared["output"]
    p.mkdir(parents=True, exist_ok=True)
    # All divisions are validated/fitted before this function is called.
    if prepared["write_first"]:
        save_gz(prepared["shadows"], prepared["locked_path"])
    if not prepared["evaluated"].empty:
        save_gz(prepared["evaluated"], p/"evaluated_games.csv.gz")
    (p/"status.json").write_text(json.dumps(
        prepared["report"], indent=2, allow_nan=False)+"\n")


def run(root: Path, now: datetime):
    if now.tzinfo is None:
        raise ValueError("Capture timestamp must be timezone-aware UTC")
    now = now.astimezone(timezone.utc)
    states = [prepare(root, sport, now) for sport in SPORTS]
    for state in states:
        persist(state)
        report = state["report"]
        print(f'{report["division"]}: first shadow locks {report["locked_first_shadow_forecasts"]}, '
              f'new {report["new_pre_tip_shadow_forecasts"]}, '
              f'D1 paired finalized {report["primary_d1_evaluated_games"]}', flush=True)
    return {s["report"]["division"]:s["report"] for s in states}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    run(args.root.resolve(), datetime.now(timezone.utc))

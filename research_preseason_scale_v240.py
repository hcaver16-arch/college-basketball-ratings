"""Courtside V240 — research-only preseason scale and scheduling-bias audit.

Historical temporal design:
  * 2024-25 D1-paired finals => frozen previous-season strength estimates.
  * 2025-26 D1-paired finals => subsequent-season test games.
  * 2025-26 month-start training windows choose fixed candidate scale/HCA
    settings using ONLY earlier 2025-26 game dates.
  * Every resulting forecast in the following month is genuinely
    *time-ordered by date* as a retrospective reconstruction, not an
    archived immutable pretip forecast.

Important limits: the 2024-25 paired archive contains no neutral-site
verification. Its prior fit treats *designated* homes as +3 by assumption.
For 2025-26, venues come from the saved ESPN score archive; its Neutral
flag is not independently verified. Thus these estimates cannot
identify true home-court advantage causally.

No modifications to live power, website, first forecasts, or schedules.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
SPORTS = ("mens-college-basketball", "womens-college-basketball")
SCALES = (0.75, 1.0, 1.25, 1.5)
HCA = (0.0, 3.0, 5.0)
FOLDS = (date(2025, 12, 1), date(2026, 1, 1),
         date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1))
END = date(2026, 4, 16)  # exclusive, matches historical source window
BASELINE = "s100_h3"
PAIRED = ("game_id", "date", "home_id", "away_id",
          "home_points", "away_points", "possessions")


def candidate_key(scale: float, home_edge: float) -> str:
    return f"s{int(round(scale * 100))}_h{int(home_edge)}"


CANDIDATES = tuple(candidate_key(scale, home) for scale in SCALES for home in HCA)


def verify_collection_status(raw: dict, season: str, sport: str) -> dict:
    if raw.get("season") != season or raw.get("sport") != sport:
        raise ValueError(f"Historical collection status has wrong season or division: {season} {sport}")
    if raw.get("last_completed_date") != ("2025-04-15" if season == "2024-25"
                                          else "2026-04-15"):
        raise ValueError(f"Unfinished historical collection for {season} {sport}")
    days = raw.get("days")
    if not isinstance(days, dict) or len(days) < 150:
        raise ValueError(f"Incomplete dated collection ledger: {season} {sport}")
    if any("error" in v for v in days.values()):
        raise ValueError(f"Source ledger contains collection errors: {season} {sport}")
    return {"season": season, "dates_logged": len(days),
            "last_completed_date": raw["last_completed_date"],
            "archived_reported_games": raw.get("games_archived"),
            "note": raw.get("notes")}


def normalize_paired(raw: pd.DataFrame, label: str) -> pd.DataFrame:
    missing = set(PAIRED) - set(raw)
    if missing:
        raise ValueError(f"{label}: missing paired-game columns {sorted(missing)}")
    frame = raw[list(PAIRED)].copy()
    for col in ("game_id", "home_id", "away_id"):
        frame[col] = frame[col].astype("string").str.strip()
    if frame[list(("game_id", "home_id", "away_id"))].isna().any().any():
        raise ValueError(f"{label}: missing game/team ID")
    if frame["game_id"].eq("").any() or frame["home_id"].eq("").any() or frame["away_id"].eq("").any():
        raise ValueError(f"{label}: empty game/team IDs")
    if frame["game_id"].duplicated().any():
        raise ValueError(f"{label}: duplicate games")
    if frame["home_id"].eq(frame["away_id"]).any():
        raise ValueError(f"{label}: same team on both sides")
    frame["day"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
    if frame["day"].isna().any():
        raise ValueError(f"{label}: invalid game date")
    for col in ("home_points", "away_points", "possessions"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if frame[list(("home_points", "away_points", "possessions"))].isna().any().any():
        raise ValueError(f"{label}: missing scores/possessions")
    if not (frame["home_points"].between(0, 250).all() and
            frame["away_points"].between(0, 250).all() and
            frame["possessions"].between(35, 120).all()):
        raise ValueError(f"{label}: unreasonable game values")
    return frame.sort_values(["day", "game_id"]).reset_index(drop=True)


def fit_frozen_prior(games: pd.DataFrame, *, ridge: float = 8.0,
                     assumed_home_edge: float = 3.0) -> dict[str, float]:
    """Full 2024-25 is earlier than any target 2025-26 game.

    Treat every prior paired record's designated home as site=Home
    because no neutral-site flag is present. This is a stated assumption.
    Ridge regularization is identical in structure to Courtside.
    """
    if games.empty or len(games) < 1000 or ridge <= 0:
        raise ValueError("Too few prior-season games or invalid ridge")
    ids = sorted(set(games["home_id"].astype(str)) | set(games["away_id"].astype(str)))
    pos = {team: ix for ix, team in enumerate(ids)}
    n = len(ids)
    lap = np.eye(n, dtype=float) * ridge
    rhs = np.zeros(n, dtype=float)
    for g in games.to_dict("records"):
        h, a = pos[str(g["home_id"])], pos[str(g["away_id"])]
        margin = float(np.clip(float(g["home_points"]-g["away_points"]), -40, 40)
                       - assumed_home_edge)
        lap[h, h] += 1
        lap[a, a] += 1
        lap[h, a] -= 1
        lap[a, h] -= 1
        rhs[h] += margin
        rhs[a] -= margin
    power = np.linalg.solve(lap, rhs)
    power -= power.mean()
    if not np.all(np.isfinite(power)):
        raise ValueError("Nonfinite historical power fit")
    return {tid: float(p) for tid, p in zip(ids, power)}


def attach_saved_2025_26_venues(paired: pd.DataFrame, saved: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Crosswalk by game ID and exact score+team IDs; fail closed on mismatches.

    This is an ESPN-derived site flag, not independent venue verification.
    Archive may include games without usable paired efficiency evidence.
    """
    needed = ("Game ID", "Home ID", "Away ID",
              "Home score", "Away score", "Venue")
    missing = set(needed) - set(saved)
    if missing:
        raise ValueError(f"Saved 2025-26 archive missing {sorted(missing)}")
    frame = saved.copy()
    for col in ("Game ID", "Home ID", "Away ID"):
        frame[col] = frame[col].astype("string").str.strip()
    frame = frame[frame["Status"].eq("Final")].copy()
    frame = frame.dropna(subset=["Game ID", "Home ID", "Away ID"])
    if frame["Game ID"].duplicated().any():
        raise ValueError("Duplicate saved 2025-26 game IDs")
    frame["Home score"] = pd.to_numeric(frame["Home score"], errors="coerce")
    frame["Away score"] = pd.to_numeric(frame["Away score"], errors="coerce")
    source = frame[list(needed)].rename(columns={
        "Game ID": "game_id", "Home ID": "saved_home_id",
        "Away ID": "saved_away_id", "Home score": "saved_home_points",
        "Away score": "saved_away_points", "Venue": "venue",
    })
    joined = paired.merge(source, on="game_id", how="left",
                          validate="one_to_one", indicator=True)
    matches = (
        joined["_merge"].eq("both")
        & joined["home_id"].astype(str).eq(joined["saved_home_id"].astype(str))
        & joined["away_id"].astype(str).eq(joined["saved_away_id"].astype(str))
        & np.isclose(joined["home_points"], joined["saved_home_points"], equal_nan=False)
        & np.isclose(joined["away_points"], joined["saved_away_points"], equal_nan=False)
        & joined["venue"].isin(("Home", "Neutral"))
    )
    matched = joined.loc[matches, list(PAIRED)+["day", "venue"]].copy()
    if len(matched) < 1000:
        raise ValueError(f"Insufficient matched 2025-26 game+site records: {len(matched)}")
    meta = {
        "historical_paired_games": len(paired),
        "score_archive_final_games": len(frame),
        "exact_game_id_team_score_venue_matches": len(matched),
        "unmatched_or_unverified_venue": int((~matches).sum()),
        "venue_provenance": "saved ESPN event neutral/home flag, NOT independently verified site evidence",
    }
    return matched.sort_values(["day", "game_id"]).reset_index(drop=True), meta


def candidate_forecasts(prior: dict, games: pd.DataFrame) -> pd.DataFrame:
    """Fixed, no-current-outcome feature matrix for every historical fixture."""
    out = games.copy()
    out["home_prior_power"] = out["home_id"].map(prior)
    out["away_prior_power"] = out["away_id"].map(prior)
    out["prior_covered"] = out["home_prior_power"].notna() & out["away_prior_power"].notna()
    out = out.loc[out["prior_covered"]].copy()
    if out.empty:
        raise ValueError("No 2025-26 games with genuine preceding-season priors")
    out["prior_gap"] = out["home_prior_power"] - out["away_prior_power"]
    out["home_designated"] = out["venue"].eq("Home").astype(int)
    out["actual_margin"] = out["home_points"] - out["away_points"]
    for scale in SCALES:
        for home in HCA:
            out[candidate_key(scale, home)] = scale*out["prior_gap"] + home*out["home_designated"]
    # When the designated home is stronger, raw home margins can be large
    # even if the physical court contributes little. This is SELECTION,
    # not a measured home-court treatment effect.
    out["home_preseason_favorite"] = out["prior_gap"] > 0
    out["preseason_gap_bucket"] = pd.cut(
        out["prior_gap"].abs(), [-np.inf, 5, 15, np.inf],
        labels=("gap_under_5", "gap_5_to_15", "gap_over_15"), right=False)
    out["site_bucket"] = np.where(out["home_designated"].eq(1), "designated_home", "ESPN_neutral")
    out["favorite_site_bucket"] = np.where(
        out["home_designated"].eq(0), "neutral",
        np.where(out["prior_gap"].gt(0), "home_preseason_favorite",
                 np.where(out["prior_gap"].lt(0),
                          "away_preseason_favorite", "prior_tie")))
    out["near_equal_prior_strength"] = out["prior_gap"].abs() < 5
    return out.reset_index(drop=True)


def _stats(frame: pd.DataFrame, prediction: str) -> dict:
    if frame.empty:
        return {"games": 0, "mae": None, "rmse": None, "signed_bias": None,
                "winner_accuracy": None, "mean_predicted_margin": None,
                "mean_actual_margin": None}
    actual = frame["actual_margin"].to_numpy(dtype=float)
    forecast = frame[prediction].to_numpy(dtype=float)
    residual = actual - forecast
    good = (actual != 0) & (forecast != 0)
    return {
        "games": len(frame),
        "mae": round(float(np.abs(residual).mean()), 4),
        "rmse": round(float(np.sqrt(np.mean(residual**2))), 4),
        "signed_bias": round(float(residual.mean()), 4),
        "winner_accuracy": (round(float((np.sign(actual[good]) ==
                                          np.sign(forecast[good])).mean()), 4)
                            if good.any() else None),
        "mean_predicted_margin": round(float(forecast.mean()), 4),
        "mean_actual_margin": round(float(actual.mean()), 4),
    }


def _selection_decomp(part: pd.DataFrame) -> dict:
    if part.empty:
        return {"games": 0}
    gap = float(part["prior_gap"].mean())
    site = float(3*part["home_designated"].mean())
    observed = float(part["actual_margin"].mean())
    residual = observed - gap - site
    if not np.isclose(observed, gap+site+residual, atol=1e-9):
        raise ValueError("Selection-site-residual identity failed")
    return {
        "games": len(part),
        "home_favorite_fraction": round(float(part["home_preseason_favorite"].mean()), 4),
        "mean_actual_designated_home_margin": round(observed, 4),
        "mean_preseason_strength_gap_selection_component": round(gap, 4),
        "assumed_3pt_home_site_contribution": round(site, 4),
        "mean_remaining_residual": round(residual, 4),
        "identity": "mean actual home margin = mean prior strength gap + assumed 3pt site term + remaining error",
    }


def _slope(part: pd.DataFrame) -> dict:
    """Descriptive calibration slope; NOT independently identified causal scale."""
    if len(part) < 30:
        return {"games": len(part), "slope": None, "intercept": None}
    x = part["prior_gap"].to_numpy(dtype=float)
    y = (part["actual_margin"]-3*part["home_designated"]).to_numpy(dtype=float)
    if float(np.var(x)) < 1e-8:
        return {"games": len(part), "slope": None, "intercept": None}
    slope = float(np.cov(x, y, bias=True)[0, 1]/np.var(x))
    offset = float(y.mean()-slope*x.mean())
    return {"games": len(part), "slope": round(slope, 4),
            "intercept": round(offset, 4),
            "meaning": "slope >1 is compatible with compressed prior gaps, but also with team turnover, selection and venue misclassification"}


def _origin_score(future: pd.DataFrame, origin: date, next_origin: date,
                  training: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    if training.empty or len(training) < 100:
        raise ValueError("Insufficient earlier-season data for a training-only fold")
    if training["day"].max() >= origin or (not future.empty and future["day"].min() < origin):
        raise ValueError("Historical fold training includes its target-date outcomes")
    errors = {name: float(np.mean(np.abs(training["actual_margin"]-training[name])))
              for name in CANDIDATES}
    # No inspection of held-out data to pick the candidate. Stable ties use
    # original fixed-candidate order, not an arbitrary future result.
    selected = min(CANDIDATES, key=lambda key: errors[key])
    test = future.copy()
    test["origin"] = str(origin)
    test["test_end_exclusive"] = str(next_origin)
    test["last_training_day"] = str(training["day"].max())
    test["training_games"] = len(training)
    test["trained_selected_model"] = selected
    test["trained_selected_prediction"] = test[selected]
    assert test.empty or (test["day"] >= origin).all()
    assert test.empty or (test["day"] < next_origin).all()
    assert test.empty or (test["last_training_day"] < test["day"].astype(str)).all()
    fold = {
        "origin": str(origin), "last_training_day": str(training["day"].max()),
        "training_games": len(training), "holdout_games": len(test),
        "selected_on_prior_dates_only": selected,
        "training_candidate_mae": {k: round(v, 4) for k, v in errors.items()},
        "training_slope": _slope(training),
        "holdout_slope_diagnostic_only": _slope(test),
        "holdout_baseline": _stats(test, BASELINE),
        "holdout_selected": _stats(test, "trained_selected_prediction"),
        "holdout_scale125_h3": _stats(test, "s125_h3"),
        "holdout_scale100_h5": _stats(test, "s100_h5"),
        "holdout_scale125_h5": _stats(test, "s125_h5"),
    }
    return test, fold


def walk_forward(fixture: pd.DataFrame, origins=FOLDS,
                 end: date = END) -> tuple[pd.DataFrame, list[dict]]:
    if fixture["game_id"].duplicated().any():
        raise ValueError("Duplicate fixture ID")
    ordered = sorted(origins)
    if not ordered or len(set(ordered)) != len(ordered):
        raise ValueError("Invalid origin sequence")
    pieces, folds = [], []
    for i, origin in enumerate(ordered):
        stop = ordered[i+1] if i+1 < len(ordered) else end
        if stop <= origin:
            raise ValueError("Non-increasing folds")
        earlier = fixture.loc[fixture["day"] < origin]
        heldout = fixture.loc[(fixture["day"] >= origin) & (fixture["day"] < stop)]
        if heldout.empty:
            continue
        predictions, summary = _origin_score(heldout, origin, stop, earlier)
        pieces.append(predictions)
        folds.append(summary)
    if not pieces:
        raise ValueError("No historical holdout games for chosen month starts")
    result = pd.concat(pieces, ignore_index=True)
    if result["game_id"].duplicated().any():
        raise ValueError("A holdout fixture was scored twice")
    return result, folds


def cohort_diagnostics(fixtures: pd.DataFrame) -> pd.DataFrame:
    columns = ("site_bucket", "favorite_site_bucket", "preseason_gap_bucket",
               "near_equal_prior_strength")
    rows = []
    for label, samples in [("all", {"all": fixtures})] + [
        (column, dict(iter(fixtures.groupby(column, observed=True))))
        for column in columns
    ]:
        for value, group in samples.items():
            if group.empty:
                continue
            for candidate in (BASELINE, "s125_h3", "s100_h5", "s125_h5",
                              "trained_selected_prediction"):
                rows.append({
                    "dimension": label, "group": str(value),
                    "model": candidate, **_stats(group, candidate),
                    "avg_preseason_gap": round(float(group["prior_gap"].mean()), 4),
                    "home_prior_favorite_fraction": round(
                        float(group["home_preseason_favorite"].mean()), 4),
                    "low_sample_under_30": len(group) < 30,
                })
    return pd.DataFrame(rows)


def audit_season(prior_games: pd.DataFrame, test_games: pd.DataFrame,
                 saved_score_archive: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    frozen = fit_frozen_prior(prior_games)
    joined, crosswalk = attach_saved_2025_26_venues(test_games, saved_score_archive)
    source = candidate_forecasts(frozen, joined)
    heldout, folds = walk_forward(source)
    if not heldout["day"].astype(str).gt(heldout["last_training_day"]).all():
        raise ValueError("Historical score leakage detected")
    cohorts = cohort_diagnostics(heldout)
    site = heldout[heldout["home_designated"] == 1]
    neutral = heldout[heldout["home_designated"] == 0]
    close = heldout[heldout["near_equal_prior_strength"]]
    result = {
        "frozen_prior_source": "2024-25 D1-only finals, ALL prior to 2025-26",
        "prior_2024_25_games": len(prior_games),
        "prior_2024_25_rated_teams": len(frozen),
        "site_match": crosswalk,
        "prior_2025_26_fixture_coverage": {
            "matched_venues": len(joined),
            "with_prior_for_both_teams": len(source),
            "not_covered": len(joined)-len(source),
        },
        "training_scheme": "For each month-start checkpoint, search 12 FIXED scale/HCA settings on earlier 2025-26 dates, then score the following month without retraining",
        "fixed_candidate_scales": list(SCALES),
        "fixed_candidate_site_intercepts": list(HCA),
        "baseline": BASELINE,
        "folds": folds,
        "holdout_games_same_candidates": len(heldout),
        "holdout_first_day": str(heldout["day"].min()),
        "holdout_last_day": str(heldout["day"].max()),
        "holdout_metrics": {name: _stats(heldout, name) for name in
                            (BASELINE, "s125_h3", "s100_h5", "s125_h5",
                             "trained_selected_prediction")},
        "selection_vs_site_components": {
            "all": _selection_decomp(heldout),
            "designated_home": _selection_decomp(site),
            "ESPN_neutral": _selection_decomp(neutral),
            "near_equal_prior_strength": _selection_decomp(close),
        },
        "descriptive_calibration_slope": {
            "all_holdout": _slope(heldout),
            "designated_home": _slope(site),
            "ESPN_neutral": _slope(neutral),
        },
        "notes": [
            "Historical 2024-25 prior is NOT an actual 2025-26 pretip saved rating; computed retrospectively from earlier-year games only.",
            "All candidates use identical historical holdout games, not team-by-team selectively filtered results.",
            "2024-25 paired D1 archive lacks neutral-site labels: its fitted prior assumes +3 for every designated home.",
            "2025-26 ESPN Neutral/Home tags crosswalk to paired D1 games but are NOT independently venue verified.",
            "The designated home team's expected margin includes team-strength selection before any hypothesized court intercept.",
            "The unexplained site residual is not causal evidence of physical home-court advantage.",
            "Training-window selected candidate is evaluated in later months ONLY, never scored on its selection window.",
            "The hypotheses were motivated by observing early 2026-27 results, therefore this 2025-26 study is retrospective research, not a fully independent holdout.",
            "No coaches, transfers or roster continuity frozen for 2025-26; scale shifts may reflect team turnover.",
            "Research-only; no automatic model promotion, official ranking changes or immutable forecast edits.",
        ],
    }
    return heldout, cohorts, result


def research_main(root: Path, out: Path):
    root, out = root.resolve(), out.resolve()
    if out == root or root in out.parents:
        rel = out.relative_to(root)
        if len(rel.parts) < 2 or rel.parts[:2] != ("data", "research_scale_v240"):
            raise ValueError("Research outputs may only use data/research_scale_v240 within repo")
    full = {
        "version": 240, "generated_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "RESEARCH_ONLY_HISTORICAL_TIME_ORDERED_NOT_PROSPECTIVE",
        "official_model_changed": False,
        "first_forecast_archive_changed": False,
        "historical_periods": {
            "prior": "2024-25", "validation": "2025-26",
            "training_before_each_origin": True,
        },
        "divisions": {},
    }
    for sport in SPORTS:
        suffix = "mens" if sport.startswith("mens") else "womens"
        paths = {
            "prior_paired": root / "data/historical_efficiency" / f"2024-25_{suffix}_paired_games.csv.gz",
            "test_paired": root / "data/historical_efficiency" / f"2025-26_{suffix}_paired_games.csv.gz",
            "prior_collection": root / "data/historical_efficiency" / f"2024-25_{suffix}_collection_status.json",
            "test_collection": root / "data/historical_efficiency" / f"2025-26_{suffix}_collection_status.json",
            "test_score_archive": root / "data/ratings" / sport / "history_2025-26.csv.gz",
        }
        if not all(p.is_file() for p in paths.values()):
            raise FileNotFoundError(f"Missing V240 historical evidence {sport}")
        statuses = {}
        for season, tag in (("2024-25", "prior_collection"), ("2025-26", "test_collection")):
            statuses[season] = verify_collection_status(
                json.loads(paths[tag].read_text()), season, sport)
        prior = normalize_paired(pd.read_csv(
            paths["prior_paired"], dtype={"game_id": str, "home_id": str, "away_id": str}),
            "2024-25 "+sport)
        test = normalize_paired(pd.read_csv(
            paths["test_paired"], dtype={"game_id": str, "home_id": str, "away_id": str}),
            "2025-26 "+sport)
        archived = pd.read_csv(paths["test_score_archive"],
                               dtype={"Game ID": str, "Home ID": str, "Away ID": str})
        joined, cohorts, result = audit_season(prior, test, archived)
        out.mkdir(parents=True, exist_ok=True)
        joined.to_csv(out / f"{suffix}_historical_walkforward.csv", index=False)
        cohorts.to_csv(out / f"{suffix}_selection_venue_cohorts.csv", index=False)
        full["divisions"][sport] = {
            "status_ledgers": statuses,
            "archived_source_sha256": {
                label: hashlib.sha256(path.read_bytes()).hexdigest()
                for label, path in paths.items()},
            **result,
        }
    (out / "summary.json").write_text(json.dumps(full, indent=2, default=str)+"\n")
    print(json.dumps(full, indent=2, default=str))
    return full


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "data/research_scale_v240")
    args = parser.parse_args()
    research_main(args.root, args.out)

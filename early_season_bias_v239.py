"""Courtside V239: non-deploying, read-only early-season forecast bias audit.

Uses saved 2025-26 score-margin priors and saved 2026-27 finals. All
candidate predictions for day D use current-season finals dated strictly
BEFORE D. Those are retrospective day-before reconstructions; historical
availability timestamps are not verified prospective locks.

No production ratings, published first forecasts, model coefficients,
power rankings, or public UI are edited. Outputs are isolated artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from early_season_calibration_v238 import (
    MODELS, ROOT, compare_chronologically, strong_win_diagnostics,
)
from prior_transition_research_v229 import (
    CAP, HOME_ADVANTAGE, SPORTS, historical_prior, metrics, normalize,
)

CAPS = (20.0, 40.0, 60.0)
CANDIDATES = (*MODELS, "anchored_cap20", "anchored_cap60",
              "legacy_hca0_fixed_rating", "legacy_hca5_fixed_rating")
MIN_INFORMATIVE = 100


def _q(value: float, cutoffs) -> str:
    """Quartiles based only on frozen 2025-26 priors for current verified D1."""
    names = ("Q1_lower", "Q2", "Q3", "Q4_upper")
    return names[int(np.searchsorted(cutoffs, value, side="right"))]


def fixed_cap_replay(prior: dict[str, float], current: pd.DataFrame,
                     selected: pd.DataFrame) -> pd.DataFrame:
    """Fit frozen ridge-8 anchored models with cap 20/40/60, before each day.

    Uses the same 3-point home treatment and regularization as V229/V238.
    Matrix updates for day D occur ONLY AFTER predicting every selected
    game on that day. Later-season team IDs are inert zero-prior nodes
    until connected to a completed earlier game.
    """
    cols = ["game_id", "anchored_cap20", "anchored_cap40", "anchored_cap60",
            "cap_fit_latest_training_day"]
    if selected.empty:
        return pd.DataFrame(columns=cols)
    teams = sorted(set(prior) | set(current["Home ID"].astype(str)) |
                   set(current["Away ID"].astype(str)))
    loc = {tid: i for i, tid in enumerate(teams)}
    n = len(teams)
    ridge = 8.0
    prior_vector = np.array([prior.get(tid, 0.0) for tid in teams], dtype=float)
    matrix = np.eye(n, dtype=float) * ridge
    rhs = {cap: ridge * prior_vector.copy() for cap in CAPS}
    grouped_selected = {day: group for day, group in selected.groupby("day")}
    results = []
    last_training_day = None
    for day, matches in current.groupby("Day", sort=True):
        label = str(day)
        if label in grouped_selected:
            fits = {cap: np.linalg.solve(matrix, rhs[cap]) for cap in CAPS}
            for game in grouped_selected[label].to_dict("records"):
                h, a = loc[str(game["home_id"])], loc[str(game["away_id"])]
                venue = 0.0 if bool(game["neutral"]) else HOME_ADVANTAGE
                preds = {f"anchored_cap{int(cap)}":
                         float(fits[cap][h] - fits[cap][a] + venue)
                         for cap in CAPS}
                results.append({"game_id": str(game["game_id"]),
                                **preds, "cap_fit_latest_training_day": last_training_day})
        # All same-day completed results join the model only AFTER prediction.
        for g in matches.to_dict("records"):
            h, a = loc[str(g["Home ID"])], loc[str(g["Away ID"])]
            margin = float(g["Home score"] - g["Away score"])
            home = 0.0 if g["Venue"] == "Neutral" else HOME_ADVANTAGE
            matrix[h, h] += 1.0
            matrix[a, a] += 1.0
            matrix[h, a] -= 1.0
            matrix[a, h] -= 1.0
            for cap in CAPS:
                adjusted = float(np.clip(margin, -cap, cap) - home)
                rhs[cap][h] += adjusted
                rhs[cap][a] -= adjusted
        last_training_day = label
    output = pd.DataFrame(results, columns=cols)
    if output["game_id"].duplicated().any() or len(output) != len(selected):
        raise ValueError("Cap sensitivity does not match selected fixtures")
    joined = selected[["game_id", "anchored_ridge8"]].merge(
        output[["game_id", "anchored_cap40"]], on="game_id",
        how="left", validate="one_to_one")
    if not np.allclose(joined["anchored_ridge8"],
                       joined["anchored_cap40"], rtol=0, atol=1e-7):
        raise ValueError("Cap 40 replay does not reproduce V238 anchored ridge-8")
    return output


def add_context(paired: pd.DataFrame, current: pd.DataFrame,
                prior: dict, d1_ids: set[str]) -> tuple[pd.DataFrame, dict]:
    """Create pregame-context labels plus clearly retrospective outcome labels."""
    if paired.empty:
        raise ValueError("No matched D1 games; refuse unsupported calibration claims")
    fixture = current[["Game ID", "Venue"]].rename(columns={"Game ID": "game_id"})
    if fixture["game_id"].duplicated().any():
        raise ValueError("Duplicate current game identifiers")
    frame = paired.merge(fixture, how="left", on="game_id",
                         validate="one_to_one")
    if frame["Venue"].isna().any():
        raise ValueError("Matched replay games missing verified venue")
    prior_d1 = np.array([float(prior[tid]) for tid in sorted(d1_ids)
                         if tid in prior], dtype=float)
    if len(prior_d1) < 200:
        raise ValueError("Insufficient previous-season D1 prior coverage")
    cutoffs = np.quantile(prior_d1, [0.25, 0.50, 0.75])
    frame["prior_home"] = frame["home_id"].map(prior).astype(float)
    frame["prior_away"] = frame["away_id"].map(prior).astype(float)
    if frame[["prior_home", "prior_away"]].isna().any().any():
        raise ValueError("A matched game has no pregame prior strength")
    frame["prior_gap_abs"] = (frame["prior_home"]-frame["prior_away"]).abs()
    frame["prior_gap_bucket"] = pd.cut(
        frame["prior_gap_abs"], [-np.inf, 5, 15, np.inf],
        labels=["under_5", "5_to_15", "over_15"], right=False,
    ).astype(str)
    frame["prior_favorite_strength"] = frame[["prior_home", "prior_away"]].max(axis=1)
    frame["prior_underdog_strength"] = frame[["prior_home", "prior_away"]].min(axis=1)
    frame["prior_favorite_quartile"] = frame["prior_favorite_strength"].map(
        lambda value: _q(value, cutoffs))
    frame["prior_opponent_quality_quartile"] = frame["prior_underdog_strength"].map(
        lambda value: _q(value, cutoffs))
    frame["location_bucket"] = np.where(frame["neutral"], "neutral", "designated_home")
    frame["preseason_favorite_site"] = np.where(
        frame["neutral"], "neutral",
        np.where(frame["prior_home"] > frame["prior_away"],
                 "home_is_prior_favorite",
                 np.where(frame["prior_home"] < frame["prior_away"],
                          "away_is_prior_favorite", "prior_tie")))
    frame["early_games_bucket"] = np.where(
        (frame["home_gp_before"] <= 2) & (frame["away_gp_before"] <= 2),
        "both_0_to_2", "either_3_plus")
    frame["blowout_outcome_bucket"] = np.where(
        frame["actual_margin"].abs() > CAP,
        "actual_margin_over_40", "actual_margin_at_most_40")
    frame["actual_margin_exceeds_40"] = frame["actual_margin"].abs() > CAP

    # Exactly additive bias accounting, not causal attribution.
    frame["residual_legacy"] = frame["actual_margin"] - frame["legacy_replay"]
    frame["actual_minus_preseason_forecast"] = (
        frame["actual_margin"] - frame["prior_only"])
    frame["preseason_forecast_minus_legacy"] = (
        frame["prior_only"] - frame["legacy_replay"])
    if not np.allclose(frame["residual_legacy"],
                       frame["actual_minus_preseason_forecast"] +
                       frame["preseason_forecast_minus_legacy"], atol=1e-10):
        raise ValueError("Prediction error identity failed")

    # Intercept-only venue sensitivities; frozen fitted team ratings.
    # This does NOT estimate optimal HCA, because ratings were fitted with HCA=3.
    frame["legacy_hca0_fixed_rating"] = frame["legacy_replay"] - np.where(
        frame["neutral"], 0.0, HOME_ADVANTAGE)
    frame["legacy_hca5_fixed_rating"] = frame["legacy_replay"] + np.where(
        frame["neutral"], 0.0, 5.0-HOME_ADVANTAGE)
    return frame, {
        "prior_2025_26_d1_team_quartile_cutoffs": [round(float(x), 4) for x in cutoffs],
        "prior_2025_26_d1_teams_with_rating": len(prior_d1),
        "preseason_opponent_quality_definition":
            "The weaker-ranked team's PRESEASON power (2025-26), not opponent performance observed after tipoff",
        "outcome_blowout_bucket_definition":
            "Post-result descriptive bucket: actual absolute margin > 40, never a pregame covariate",
    }


def add_cap_candidates(frame: pd.DataFrame, cap_predictions: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or cap_predictions.empty:
        raise ValueError("Cap candidates or matched fixture sample missing")
    out = frame.merge(cap_predictions, on="game_id", validate="one_to_one")
    if len(out) != len(frame):
        raise ValueError("Cap forecasts do not cover precisely the V238 fixtures")
    if not np.allclose(out["anchored_cap40"], out["anchored_ridge8"],
                       rtol=0, atol=1e-7):
        raise ValueError("V238 reference cap 40 changed")
    leaks = out["cap_fit_latest_training_day"].notna() & (
        out["cap_fit_latest_training_day"] >= out["day"])
    if leaks.any():
        raise ValueError("Cap replay used same/future-day results")
    return out


def _segment_metrics(group: pd.DataFrame, label: str, bucket: str) -> list[dict]:
    sample = group.to_dict("records")
    a = float(group["actual_margin"].mean())
    rows = []
    for name in CANDIDATES:
        stat = metrics(sample, name)
        rows.append({
            "dimension": label, "bucket": str(bucket), "model": name,
            "games": int(stat["games"]),
            "mae": stat["mae"], "rmse": stat["rmse"],
            "winner_accuracy": stat["winner_accuracy"], "signed_bias": stat["bias"],
            "avg_actual_home_margin": round(a, 4),
            "avg_predicted_home_margin": round(float(group[name].mean()), 4),
            "avg_actual_minus_prior": round(
                float(group["actual_minus_preseason_forecast"].mean()), 4),
            "avg_prior_minus_legacy": round(
                float(group["preseason_forecast_minus_legacy"].mean()), 4),
            "low_sample_under_20": bool(len(group) < 20),
        })
    return rows


def breakdowns(frame: pd.DataFrame) -> pd.DataFrame:
    """Breakdowns share the same fixtures within each segment and division."""
    dimensions = (
        "location_bucket", "preseason_favorite_site",
        "prior_favorite_quartile", "prior_opponent_quality_quartile",
        "prior_gap_bucket", "early_games_bucket", "blowout_outcome_bucket",
    )
    rows = _segment_metrics(frame, "all_games", "all")
    for column in dimensions:
        for key, part in frame.groupby(column, dropna=False, sort=True):
            rows.extend(_segment_metrics(part, column, str(key)))
    return pd.DataFrame(rows)


def _bias_summary(part: pd.DataFrame, model: str) -> dict:
    if part.empty:
        return {"games": 0, "mae": None, "signed_bias": None,
                "win_accuracy": None, "avg_prediction": None,
                "avg_actual": None}
    stats = metrics(part.to_dict("records"), model)
    return {"games": len(part), "mae": stats["mae"],
            "signed_bias": stats["bias"],
            "win_accuracy": stats["winner_accuracy"],
            "avg_prediction": round(float(part[model].mean()), 4),
            "avg_actual": round(float(part["actual_margin"].mean()), 4)}


def report_one_division(prior: dict, current: pd.DataFrame,
                        d1_ids: set[str], asof: date):
    paired, replay, states = compare_chronologically(
        prior, current, d1_ids, asof)
    frame, context = add_context(paired, current, prior, d1_ids)
    cap = fixed_cap_replay(prior, current, frame)
    frame = add_cap_candidates(frame, cap)
    segments = breakdowns(frame)
    strong = strong_win_diagnostics(prior, current, states, d1_ids)
    if not strong.empty:
        cutoffs = context["prior_2025_26_d1_team_quartile_cutoffs"]
        strong["opponent_prior_quality_quartile"] = strong["opponent_prior_power"].map(
            lambda v: _q(float(v), cutoffs) if pd.notna(v) else "prior_unknown")
        strong["win_exceeds_40_cap"] = strong["winning_margin"] > CAP

    overall = {name: _bias_summary(frame, name) for name in CANDIDATES}
    home = frame.loc[~frame["neutral"]]
    neutral = frame.loc[frame["neutral"]]
    above40 = frame.loc[frame["actual_margin_exceeds_40"]]
    below40 = frame.loc[~frame["actual_margin_exceeds_40"]]
    return frame, segments, strong, {
        "matched_games": len(frame),
        "v238_day_before_reference_matched_games": replay["matched_d1_games"],
        "informative_v238_disagreements": replay["informative_model_disagreement_games"],
        "comparison_status": replay["status"],
        "prior_context": context,
        "overall_model_metrics": overall,
        "non_neutral_intercept_only_hca_sensitivity": {
            "baseline_3": _bias_summary(home, "legacy_replay"),
            "intercept_0": _bias_summary(home, "legacy_hca0_fixed_rating"),
            "intercept_5": _bias_summary(home, "legacy_hca5_fixed_rating"),
            "neutral_games_control_count": len(neutral),
        },
        "retrospective_cap_outcome_buckets": {
            "abs_final_margin_over_40": {
                "games": len(above40),
                "legacy": _bias_summary(above40, "legacy_replay"),
                "anchored_cap20": _bias_summary(above40, "anchored_cap20"),
                "anchored_cap40": _bias_summary(above40, "anchored_ridge8"),
                "anchored_cap60": _bias_summary(above40, "anchored_cap60"),
            },
            "abs_final_margin_at_most_40": {
                "games": len(below40),
                "legacy": _bias_summary(below40, "legacy_replay"),
            },
        },
        "exact_signed_error_decomposition": {
            "avg_actual_minus_prior_only": round(
                float(frame["actual_minus_preseason_forecast"].mean()), 5),
            "avg_prior_only_minus_legacy": round(
                float(frame["preseason_forecast_minus_legacy"].mean()), 5),
            "avg_actual_minus_legacy": round(
                float(frame["residual_legacy"].mean()), 5),
            "identity": "actual - legacy = (actual - prior_only) + (prior_only - legacy)",
        },
        "strong_wins_25_plus": {
            "observed_d1_team_wins": len(strong),
            "legacy_postday_drops": (
                int(strong["legacy_dropped_after_win"].sum()) if len(strong) else 0),
            "anchored8_postday_drops": (
                int((strong["anchored8_change_after_day"] < -0.025).sum())
                if len(strong) else 0),
        },
        "disagreement_sufficiency": {
            "threshold": MIN_INFORMATIVE,
            "v238_informative": replay["informative_model_disagreement_games"],
            "ready_for_exploratory_review": bool(
                replay["informative_model_disagreement_games"] >= MIN_INFORMATIVE),
            "independent_prospective_validation_sufficient": False,
        },
    }


def research_main(root: Path, output: Path, asof: date,
                  d1_lookup=None):
    """Read saved inputs, write only isolated artifacts. Never update production."""
    root = root.resolve()
    output = output.resolve()
    if output == root or root in output.parents:
        rel = output.relative_to(root)
        if len(rel.parts) < 2 or rel.parts[:2] != ("data", "research_bias_v239"):
            raise ValueError("Repo output restricted to data/research_bias_v239/")
    if asof < date(2026, 11, 1):
        raise ValueError("2026-27 analysis cannot predate the season")
    from reliability_v99 import fetch_d1_membership
    lookup = d1_lookup or fetch_d1_membership
    result = {
        "version": 239, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "asof": str(asof), "status": "RESEARCH_ONLY_NOT_DEPLOYED",
        "model_change": False, "official_forecast_change": False,
        "source": "saved previous/current ESPN results, verified current ESPN D1 directory",
        "divisions": {},
        "limitations": [
            "Retrospective date-only V238-matched replay; NOT true immutable pretip forecasts.",
            "All results from target day D are held out for all candidate fits on that day.",
            "HCA sensitivities change only the intercept, with existing 3-point-fitted team ratings held fixed; NOT a separately refitted home-advantage estimate.",
            "Actual >40-point outcomes define a POSTGAME diagnostic group, NOT a pregame known feature.",
            "Candidate cap20/40/60 solves use only completed prior days; all share frozen ridge=8, home advantage=3 and 2025-26 prior.",
            "Opponent-quality quartiles use weaker side's 2025-26 prior among current D1 programs; not independently measured 2026-27 quality.",
            "Current ESPN D1 membership is not an independently reconstructed historical 2025-26 membership census.",
            "Saved current-season finals may lack historical point-in-time availability timestamps or be incomplete; no live ESPN refresh or postgame backfill.",
            "The error decomposition is algebraically exact but NOT a causal attribution of errors to home advantage, opponent strength or roster moves.",
            "These hypotheses were selected with previous early-season results in view; no coefficient selection or promotion from this sample.",
            "No change to rating_engine.py, daily_ratings.py, V97/V233/V235, model outputs, public rankings or site UI.",
        ],
    }
    for sport in SPORTS:
        base = root / "data" / "ratings" / sport
        sources = {
            "prior_results": base / "history_2025-26.csv.gz",
            "current_results": base / "season_2026-27.csv.gz",
            "official_saved_ratings": base / "latest.csv.gz",
            "rating_status": base / "status.json",
        }
        if not all(p.is_file() for p in sources.values()):
            raise FileNotFoundError(f"Missing archived rating evidence: {sport}")
        previous = normalize(pd.read_csv(
            sources["prior_results"], dtype={"Game ID": str, "Home ID": str, "Away ID": str}), "prior")
        current = normalize(pd.read_csv(
            sources["current_results"], dtype={"Game ID": str, "Home ID": str, "Away ID": str}), "current")
        current = current[(current["Day"] >= date(2026, 11, 1)) &
                          (current["Day"] <= asof)].copy()
        prior = historical_prior(previous)
        ids = set(map(str, lookup(sport)))
        paired, cohort, wins, stats = report_one_division(prior, current, ids, asof)
        tag = "mens" if sport.startswith("mens") else "womens"
        output.mkdir(parents=True, exist_ok=True)
        paired.to_csv(output / f"{tag}_paired_bias.csv", index=False)
        cohort.to_csv(output / f"{tag}_cohort_metrics.csv", index=False)
        wins.to_csv(output / f"{tag}_strong_wins_context.csv", index=False)
        result["divisions"][sport] = {
            "archived_input_hashes_sha256": {
                name: hashlib.sha256(path.read_bytes()).hexdigest()
                for name, path in sources.items()},
            "saved_rating_status": json.loads(sources["rating_status"].read_text()),
            "verified_current_d1_count": len(ids),
            "prior_archived_finals": len(previous),
            "current_archived_finals_at_asof": len(current),
            **stats,
        }
    (output / "summary.json").write_text(
        json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps(result, indent=2, default=str))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "data" / "research_bias_v239")
    parser.add_argument("--asof", type=date.fromisoformat,
                        default=datetime.now(timezone.utc).date())
    args = parser.parse_args()
    research_main(args.root, args.out, args.asof)

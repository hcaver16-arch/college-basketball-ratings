"""V246 research-only: chronological opponent-quality/home-favorite calibration.

Historical 2025-26 V240 prior-only forecasts are the *only* model-selection
data. Archived 2026-27 verified first forecasts are independently audited,
NEVER refitted or represented as prospective tests of new candidates.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
RIDGE = 250.0
MIN_TRAIN = 100
BASE = "s100_h3"
FEATURES = ("home_favorite_site", "weak_opponent_home", "strong_gap_home")
CANDIDATES = ("baseline", "intercept", "home_favorite", "opponent_interaction")
DIVISIONS = {"mens": "mens-college-basketball", "womens": "womens-college-basketball"}


def design(frame: pd.DataFrame) -> np.ndarray:
    required = {"prior_gap", "home_designated", "home_prior_power",
                "away_prior_power", BASE}
    if missing := required - set(frame):
        raise ValueError(f"Missing historical pregame fields: {sorted(missing)}")
    gap = pd.to_numeric(frame["prior_gap"], errors="raise").to_numpy(float)
    home = pd.to_numeric(frame["home_designated"], errors="raise").to_numpy(float)
    away_power = pd.to_numeric(frame["away_prior_power"], errors="raise").to_numpy(float)
    if not np.isfinite(np.column_stack([gap, home, away_power])).all():
        raise ValueError("Nonfinite pregame predictors")
    # Frozen historical-prior strength, never current outcomes.
    # Negative away prior = weaker opponent; cap to limit extrapolation.
    return np.column_stack([np.ones(len(frame)), home * (gap > 0),
                            home * (gap > 0) * np.clip(-away_power, 0, 25)/10,
                            home * np.clip(gap, 0, 25)/10])


def predict(train: pd.DataFrame, test: pd.DataFrame, candidate: str) -> np.ndarray:
    baseline = test[BASE].to_numpy(float)
    if candidate == "baseline":
        return baseline
    if candidate not in CANDIDATES:
        raise ValueError("Unknown candidate")
    if len(train) < MIN_TRAIN:
        raise ValueError("Too few earlier games")
    X, T = design(train), design(test)
    n = {"intercept": 1, "home_favorite": 2, "opponent_interaction": 4}[candidate]
    residual = train["actual_margin"].to_numpy(float) - train[BASE].to_numpy(float)
    penalty = np.eye(n) * RIDGE
    penalty[0, 0] = 0.0
    coef = np.linalg.solve(X[:, :n].T @ X[:, :n] + penalty,
                           X[:, :n].T @ residual)
    return baseline + T[:, :n] @ coef


def score(actual, pred) -> dict:
    actual, pred = np.asarray(actual, float), np.asarray(pred, float)
    if len(actual) == 0 or not (np.isfinite(actual).all() and np.isfinite(pred).all()):
        raise ValueError("Missing/invalid scores")
    good = (actual != 0) & (pred != 0)
    return {"games": len(actual), "mae": round(float(np.abs(actual-pred).mean()), 4),
            "bias": round(float((actual-pred).mean()), 4),
            "winner_accuracy": round(float((np.sign(actual[good]) ==
                np.sign(pred[good])).mean()), 4) if good.any() else None}


def historical(frame: pd.DataFrame) -> dict:
    if frame.empty or frame["game_id"].duplicated().any():
        raise ValueError("Missing/duplicate historical games")
    required = {"day", "origin", "last_training_day", "actual_margin", BASE}
    if missing := required-set(frame):
        raise ValueError(f"Missing V240 time-order evidence: {sorted(missing)}")
    data = frame.copy()
    data["day"] = pd.to_datetime(data["day"], errors="raise")
    data["origin"] = pd.to_datetime(data["origin"], errors="raise")
    data["last_training_day"] = pd.to_datetime(data["last_training_day"], errors="raise")
    if ((data["last_training_day"] >= data["origin"]) |
        (data["origin"] > data["day"])).any():
        raise ValueError("V240 holdout provenance fails temporal validation")
    # V240 output contains only held-out games, not the full earlier training
    # fixture. Hence use strictly *earlier held-out games* as calibration data.
    # The first fold is a baseline-only burn-in, not a tuned evaluation fold.
    folds = []
    evaluated = []
    for origin in sorted(data["origin"].unique()):
        train = data[data["day"] < origin]
        test = data[data["origin"] == origin]
        if test.empty:
            continue
        if len(train) < MIN_TRAIN:
            folds.append({"origin": str(pd.Timestamp(origin).date()),
                          "status": "burn_in_no_training", "games": len(test)})
            continue
        if train["day"].max() >= origin or test["day"].min() < origin:
            raise ValueError("Training/holdout date leakage")
        outputs = {name: predict(train, test, name) for name in CANDIDATES}
        scores = {name: score(test["actual_margin"], values)
                  for name, values in outputs.items()}
        folds.append({"origin": str(pd.Timestamp(origin).date()),
                      "training_games": len(train), "last_training_day":
                      str(train["day"].max().date()), "holdout": scores})
        result = test[["game_id", "day", "origin", "actual_margin", BASE,
                       "prior_gap", "home_designated"]].copy()
        for name, values in outputs.items():
            result[name] = values
        evaluated.append(result)
    if not evaluated:
        raise ValueError("No evaluable historical folds after burn-in")
    combined = pd.concat(evaluated, ignore_index=True)
    overall = {name: score(combined["actual_margin"], combined[name])
               for name in CANDIDATES}
    overall["note"] = "Same held-out games; fixed candidates; first fold excluded as burn-in"
    return {"folds": folds, "overall": overall, "evaluated_games": len(combined),
            "first_fold_not_scored": True}


def prospective_audit(frame: pd.DataFrame) -> dict:
    # Calls the exact V242 timestamp-verifying logic. This is an observational
    # diagnostic only: no V246 candidate was archived pretip.
    from prediction_accuracy_v242 import accuracy_rows
    data, rejected = accuracy_rows(frame)
    if data.empty:
        return {"games": 0, "rejected_timestamp_rows": rejected}
    pred = data["Baseline home margin"].to_numpy(float)
    actual = data["Actual home margin"].to_numpy(float)
    out = {"games": len(data), "rejected_timestamp_rows": rejected,
           "official_first_forecast": score(actual, pred),
           "home_favorites": score(actual[pred > 0], pred[pred > 0]) if (pred > 0).any() else None,
           "away_favorites": score(actual[pred < 0], pred[pred < 0]) if (pred < 0).any() else None,
           "candidate_scores": None,
           "reason": "V246 alternatives were not timestamped before these games; never score them as prospective forecasts"}
    return out


def run(root: Path, out: Path) -> dict:
    from live_performance_v123 import _read
    result = {"version": 246, "status": "RESEARCH_ONLY_NOT_DEPLOYED",
              "production_changed": False, "divisions": {}}
    for division, sport in DIVISIONS.items():
        path = root/"data/research_scale_v240"/f"{division}_historical_walkforward.csv"
        if not path.is_file():
            raise FileNotFoundError(f"Run V240 first: {path}")
        history = pd.read_csv(path, dtype={"game_id": str})
        _, saved = _read(sport)
        result["divisions"][division] = {
            "historical": historical(history),
            "prospective_first_forecast_audit": prospective_audit(saved)}
    result["limitations"] = [
        "V240 historical venue labels from ESPN are not independently verified.",
        "Historical calibration trains on earlier V240 holdouts only; first fold is burn-in.",
        "Historical model is frozen prior-only, not the current Courtside production model.",
        "No V246 candidates have immutable pretip predictions; prospective archive is observational baseline only.",
        "No inference of causal home-court advantage; schedule selection and opponent strength are confounded.",
        "No production promotion without independent prospective validation."]
    out.mkdir(parents=True, exist_ok=True)
    (out/"summary.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=ROOT/"data/research_interaction_v246")
    args = parser.parse_args()
    run(args.root.resolve(), args.out.resolve())

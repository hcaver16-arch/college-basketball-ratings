"""V245: read-only, stratified home-favorite forecast-error investigation.

Reuses V239's date-ordered replay and frozen preseason priors. Venue labels
are from saved ESPN game records, NOT independently audited venue evidence.
Descriptive within-stratum comparisons do not identify causal HCA.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
MIN_N = 20
BASE = "anchored_cap40"
REQUIRED = {"game_id", "day", "cap_fit_latest_training_day", "neutral",
            "prior_home", "prior_away", "prior_opponent_quality_quartile",
            "prior_gap_bucket", "early_games_bucket", "actual_margin", BASE,
            "anchored_ridge8", "home_gp_before", "away_gp_before"}


def normalize_venue(series):
    def parse(value):
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if str(value).strip().lower() in ("true", "1"):
            return True
        if str(value).strip().lower() in ("false", "0"):
            return False
        raise ValueError(f"Unverified/missing neutral-site flag: {value!r}")
    return series.map(parse)


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    if missing := REQUIRED - set(frame):
        raise ValueError(f"Missing V239 evidence columns: {sorted(missing)}")
    if frame.empty or frame["game_id"].isna().any() or frame["game_id"].duplicated().any():
        raise ValueError("Empty, missing, or duplicate game IDs")
    out = frame.copy()
    out["neutral"] = normalize_venue(out["neutral"])
    numeric = ["prior_home", "prior_away", "actual_margin", BASE, "anchored_ridge8",
               "home_gp_before", "away_gp_before"]
    out[numeric] = out[numeric].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(out[numeric].to_numpy(dtype=float)).all():
        raise ValueError("Nonfinite numeric evidence")
    if not np.allclose(out[BASE], out["anchored_ridge8"], atol=1e-7, rtol=0):
        raise ValueError("Cap40 replay no longer matches V238 reference")
    day = pd.to_datetime(out["day"], errors="raise")
    trained = pd.to_datetime(out["cap_fit_latest_training_day"], errors="coerce")
    if (trained.notna() & (trained >= day)).any():
        raise ValueError("Same/future-day training leakage")
    if out[["prior_opponent_quality_quartile", "prior_gap_bucket",
            "early_games_bucket"]].isna().any().any():
        raise ValueError("Missing preseason stratum")
    out["venue"] = np.where(out["neutral"], "neutral", "designated_home")
    out["preseason_favorite"] = np.where(out["prior_home"] > out["prior_away"],
        "home", np.where(out["prior_home"] < out["prior_away"], "away", "tie"))
    out["forecast_favorite"] = np.where(out[BASE] > 0, "home",
        np.where(out[BASE] < 0, "away", "tie"))
    out["predicted_margin_band"] = pd.cut(out[BASE].abs(),
        [-0.001, 5, 10, 20, np.inf], labels=["0_to_5", "5_to_10", "10_to_20", "20_plus"])
    out["error"] = out["actual_margin"] - out[BASE]
    out["abs_error"] = out["error"].abs()
    return out


def summarize(frame: pd.DataFrame, by: list[str]) -> list[dict]:
    rows = []
    for keys, part in frame.groupby(by, observed=True, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        n = len(part)
        e = part["error"].to_numpy(dtype=float)
        rows.append({**dict(zip(by, map(str, keys))), "games": n,
            "signed_bias": round(float(e.mean()), 4),
            "mae": round(float(np.abs(e).mean()), 4),
            "bias_se": round(float(np.std(e, ddof=1)/np.sqrt(n)), 4) if n > 1 else None,
            "avg_actual_margin": round(float(part["actual_margin"].mean()), 4),
            "avg_predicted_margin": round(float(part[BASE].mean()), 4),
            "low_sample": n < MIN_N})
    return rows


def matched_context(frame: pd.DataFrame) -> list[dict]:
    # Compare home vs away preseason favorites within SAME venue and
    # preseason strength-gap, opponent-quality and game-experience strata.
    keys = ["venue", "prior_opponent_quality_quartile",
            "prior_gap_bucket", "early_games_bucket"]
    results = []
    for values, part in frame.groupby(keys, observed=True):
        home = part[part["preseason_favorite"] == "home"]
        away = part[part["preseason_favorite"] == "away"]
        if home.empty or away.empty:
            continue
        n1, n2 = len(home), len(away)
        results.append({**dict(zip(keys, map(str, values))),
            "home_prior_favorite_games": n1, "away_prior_favorite_games": n2,
            "home_prior_favorite_bias": round(float(home["error"].mean()), 4),
            "away_prior_favorite_bias": round(float(away["error"].mean()), 4),
            "home_minus_away_bias": round(float(home["error"].mean()-away["error"].mean()), 4),
            "low_sample": min(n1, n2) < MIN_N})
    return results


def analyze(frame: pd.DataFrame, division: str) -> dict:
    data = prepare(frame)
    nonneutral = data[~data["neutral"]]
    return {"division": division, "games": len(data),
        "all_by_venue": summarize(data, ["venue"]),
        "venue_by_forecast_favorite": summarize(data, ["venue", "forecast_favorite"]),
        "designated_home_by_margin_and_quality": summarize(
            nonneutral, ["forecast_favorite", "predicted_margin_band",
                         "prior_opponent_quality_quartile"]),
        "designated_home_by_preseason_gap": summarize(
            nonneutral, ["preseason_favorite", "prior_gap_bucket"]),
        "matched_preseason_context": matched_context(data),
        "limitations": [
            "Saved ESPN neutral/designated-home labels have not been independently verified.",
            "Home/away schedule assignment and opponent quality are not randomized; differences are associations, not causal HCA.",
            "Preseason quartiles and gaps use frozen previous-season priors, not future results.",
            "Same-day results excluded from replay, but historical forecast timestamps were not archived.",
            "Small cells (<20 games) flagged; do not rank or calibrate from sparse slices.",
            "No official model changes or promotion before independent prospective validation."]}


def research_main(root: Path, out: Path):
    root, out = root.resolve(), out.resolve()
    if out == root or root in out.parents:
        relative = out.relative_to(root)
        if len(relative.parts) < 2 or relative.parts[:2] != ("data", "research_home_context_v245"):
            raise ValueError("V245 output restricted to data/research_home_context_v245/")
    result = {"version": 245, "status": "RESEARCH_ONLY_NOT_DEPLOYED",
              "production_changed": False, "divisions": {}}
    for division in ("mens", "womens"):
        path = root/"data/research_bias_v239"/f"{division}_paired_bias.csv"
        if not path.is_file():
            raise FileNotFoundError(f"First generate V239 evidence: {path}")
        frame = pd.read_csv(path, dtype={"game_id": str})
        result["divisions"][division] = analyze(frame, division)
    out.mkdir(parents=True, exist_ok=True)
    (out/"summary.json").write_text(json.dumps(result, indent=2)+"\n")
    for division, section in result["divisions"].items():
        pd.DataFrame(section["matched_preseason_context"]).to_csv(
            out/f"{division}_matched_context.csv", index=False)
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=ROOT/"data/research_home_context_v245")
    args = parser.parse_args()
    research_main(args.root, args.out)

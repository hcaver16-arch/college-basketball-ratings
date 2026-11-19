"""V244: compare historical model candidates on *matched* games within each study.

V240 = 2025-26 historical scale/HCA holdout; V239 = 2026-27
retrospective day-before cap replay. Never rank across these two cohorts.
No official predictions or rating files are written.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
SCALE = ("s100_h3", "s125_h3", "s150_h3", "trained_selected_prediction")
CAP = ("anchored_cap20", "anchored_cap40", "anchored_cap60")
MIN_GAMES = 30


def evaluate_matched(frame: pd.DataFrame, models: tuple[str, ...],
                     actual_col: str, *, reference: str) -> list[dict]:
    required = set(models) | {actual_col, "game_id"}
    if missing := required - set(frame):
        raise ValueError(f"Missing candidate evidence: {sorted(missing)}")
    if frame["game_id"].isna().any() or frame["game_id"].duplicated().any():
        raise ValueError("Missing or duplicate game ID")
    if frame.empty:
        raise ValueError("No matched historical games")
    # A single common complete-case cohort, never candidate-specific subsets.
    numeric = frame[[actual_col, *models]].apply(pd.to_numeric, errors="coerce")
    valid = np.isfinite(numeric.to_numpy(dtype=float)).all(axis=1)
    if not valid.all():
        raise ValueError("Incomplete/nonfinite candidate evidence; refuse unequal cohorts")
    actual = numeric[actual_col].to_numpy(dtype=float)
    base = numeric[reference].to_numpy(dtype=float)
    base_mae = float(np.abs(actual-base).mean())
    out = []
    for name in models:
        pred = numeric[name].to_numpy(dtype=float)
        error = actual-pred
        decisive = (actual != 0) & (pred != 0)
        out.append({"model": name, "games": len(actual),
            "mae": round(float(np.abs(error).mean()), 4),
            "delta_mae_vs_reference": round(float(np.abs(error).mean()-base_mae), 4),
            "signed_bias": round(float(error.mean()), 4),
            "winner_accuracy": round(float(np.mean(np.sign(actual[decisive]) ==
                                       np.sign(pred[decisive]))), 4) if decisive.any() else None,
            "low_sample": len(actual) < MIN_GAMES})
    return out


def verify_v240(frame):
    required = {"day", "last_training_day", "origin", "game_id"}
    if missing := required-set(frame):
        raise ValueError(f"V240 temporal evidence missing {sorted(missing)}")
    days = pd.to_datetime(frame["day"], errors="raise")
    last = pd.to_datetime(frame["last_training_day"], errors="raise")
    origin = pd.to_datetime(frame["origin"], errors="raise")
    if not ((last < origin) & (origin <= days)).all():
        raise ValueError("V240 time-ordered fold violation")


def verify_v239(frame):
    required = {"day", "cap_fit_latest_training_day", "anchored_ridge8", "anchored_cap40"}
    if missing := required-set(frame):
        raise ValueError(f"V239 evidence missing {sorted(missing)}")
    days = pd.to_datetime(frame["day"], errors="raise")
    last = pd.to_datetime(frame["cap_fit_latest_training_day"], errors="coerce")
    if (last.notna() & (last >= days)).any():
        raise ValueError("V239 replay uses same/future-day result")
    if not np.allclose(frame["anchored_ridge8"], frame["anchored_cap40"],
                       rtol=0, atol=1e-7):
        raise ValueError("V239 cap40 reference no longer reproduces V238 anchored8")


def compare(sport: str, v240: pd.DataFrame, v239: pd.DataFrame) -> dict:
    verify_v240(v240)
    verify_v239(v239)
    scale = evaluate_matched(v240, SCALE, "actual_margin", reference="s100_h3")
    cap = evaluate_matched(v239, CAP, "actual_margin", reference="anchored_cap40")
    # Avoid claim that outcome-defined blowouts are prospective features.
    cap_groups = []
    for name, group in (("actual_at_most_40", v239[v239["actual_margin"].abs() <= 40]),
                        ("actual_over_40", v239[v239["actual_margin"].abs() > 40])):
        if not group.empty:
            cap_groups.append({"outcome_bucket": name,
                "results": evaluate_matched(group, CAP, "actual_margin",
                                            reference="anchored_cap40")})
    return {"division": sport,
        "scale_study": {"period": "2025-26 monthly time-ordered holdout",
            "reference": "s100_h3", "results": scale,
            "limitations": "Frozen 2024-25 prior; venue tags not independently verified; fixed prior-only scale candidates."},
        "cap_study": {"period": "2026-27 retrospective day-before replay",
            "reference": "anchored_cap40", "results": cap,
            "outcome_only_buckets": cap_groups,
            "limitations": "Retrospective reconstructions, not immutable pretip forecasts; hypotheses already informed by 2026-27 results."},
        "comparison_warning": "Different seasons and model families: NEVER rank V239 cap vs V240 scale directly.",
        "production_change": False, "candidate_promotion": False}


def research_main(root: Path, out: Path):
    root, out = root.resolve(), out.resolve()
    if out == root or root in out.parents:
        rel = out.relative_to(root)
        if len(rel.parts) < 2 or rel.parts[:2] != ("data", "research_comparison_v244"):
            raise ValueError("V244 output must stay in data/research_comparison_v244/")
    report = {"version": 244, "status": "RESEARCH_ONLY_NOT_DEPLOYED",
              "official_ratings_changed": False, "official_forecasts_changed": False,
              "divisions": {}, "limitations": [
                "V239 and V240 use different seasons; compare candidates only within their own matched cohort.",
                "V239 is date-ordered retrospective replay, not verified immutable pre-tip archive.",
                "V240 prior-only model and V239 anchored replay are different model families.",
                "Blowout buckets are defined by final scores and are diagnostic only.",
                "Hypotheses were motivated by current-season evidence; historical comparison is exploratory.",
                "No automatic deployment or model selection before independent prospective evaluation."]}
    for division in ("mens", "womens"):
        p240 = root / "data/research_scale_v240" / f"{division}_historical_walkforward.csv"
        p239 = root / "data/research_bias_v239" / f"{division}_paired_bias.csv"
        if not p240.is_file() or not p239.is_file():
            raise FileNotFoundError(f"Generate existing V240 and V239 research artifacts first: {p240}, {p239}")
        a = pd.read_csv(p240, dtype={"game_id": str})
        b = pd.read_csv(p239, dtype={"game_id": str})
        report["divisions"][division] = compare(division, a, b)
    out.mkdir(parents=True, exist_ok=True)
    (out/"summary.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=ROOT/"data/research_comparison_v244")
    args = parser.parse_args()
    research_main(args.root, args.out)

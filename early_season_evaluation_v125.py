"""V125: read-only, prospective early-season evaluation for both divisions.

Uses only saved first forecasts and separately timestamped pre-tip roster predictions.
Does not train, optimize, backfill predictions, or alter the rating engine.
"""
import json
from pathlib import Path
import pandas as pd

SPORTS = ("mens-college-basketball", "womens-college-basketball")


def evaluate(root=Path(".")):
    results = {}
    for sport in SPORTS:
        base = Path(root) / "data" / "predictions" / sport
        forecast_path = base / "first_forecasts.csv.gz"
        evaluated_path = base / "evaluated_games.csv.gz"
        report = {"sport": sport, "status": "awaiting_finals", "graded_d1_games": 0,
                  "paired_d1_games": 0, "notes": []}
        if not forecast_path.exists():
            report["status"] = "missing_forecast_archive"
            results[sport] = report
            continue
        forecast = pd.read_csv(forecast_path, compression="gzip", dtype={"Game ID": str})
        report["locked_first_forecasts"] = len(forecast)
        if not evaluated_path.exists():
            results[sport] = report
            continue
        data = pd.read_csv(evaluated_path, compression="gzip", dtype={"Game ID": str})
        required = {"Game ID", "Game start UTC", "First forecast UTC", "Baseline home margin",
                    "Actual home margin", "Matchup class"}
        if not required.issubset(data):
            report["status"] = "invalid_evaluation_schema"
            report["notes"] = sorted(required - set(data))
            results[sport] = report
            continue
        start = pd.to_datetime(data["Game start UTC"], utc=True, errors="coerce")
        first = pd.to_datetime(data["First forecast UTC"], utc=True, errors="coerce")
        valid = start.notna() & first.notna() & (first < start)
        report["rejected_non_pretip_rows"] = int((~valid).sum())
        d1 = data.loc[valid & data["Matchup class"].eq("D1 vs D1")].drop_duplicates("Game ID").copy()
        for field in ("Baseline home margin", "Actual home margin", "Later roster margin"):
            if field in d1:
                d1[field] = pd.to_numeric(d1[field], errors="coerce")
        d1 = d1.dropna(subset=["Baseline home margin", "Actual home margin"])
        report["graded_d1_games"] = len(d1)
        if d1.empty:
            results[sport] = report
            continue
        report["status"] = "preliminary" if len(d1) < 100 else "review_sample_reached"
        actual = d1["Actual home margin"]
        pred = d1["Baseline home margin"]
        report["baseline_mae"] = round(float((actual - pred).abs().mean()), 4)
        elig = (actual != 0) & (pred != 0)
        report["baseline_winner_sample"] = int(elig.sum())
        report["baseline_winner_accuracy"] = round(float(((actual[elig] > 0) == (pred[elig] > 0)).mean()), 4) if elig.any() else None
        if "Later roster margin" in d1 and "Roster forecast UTC" in d1:
            roster_time = pd.to_datetime(d1["Roster forecast UTC"], utc=True, errors="coerce")
            starts = pd.to_datetime(d1["Game start UTC"], utc=True, errors="coerce")
            paired = d1.loc[roster_time.notna() & (roster_time < starts) & d1["Later roster margin"].notna()].copy()
            report["paired_d1_games"] = len(paired)
            if len(paired):
                a = paired["Actual home margin"]
                b = paired["Baseline home margin"]
                r = paired["Later roster margin"]
                report["paired_baseline_mae"] = round(float((a - b).abs().mean()), 4)
                report["paired_roster_mae"] = round(float((a - r).abs().mean()), 4)
                report["paired_roster_minus_baseline_mae"] = round(report["paired_roster_mae"] - report["paired_baseline_mae"], 4)
        report["notes"].append("Observational only; 100 D1 games is a review checkpoint, not evidence for promotion.")
        results[sport] = report
    return results


if __name__ == "__main__":
    data = evaluate()
    print(json.dumps(data, indent=2))
    import os
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as out:
            out.write("## Courtside V125 — Early-season model evaluation\n\n")
            for sport, report in data.items():
                out.write(f"### {sport}\n\n")
                out.write(f"- Status: **{report['status']}**\n")
                out.write(f"- Graded D1 games: {report['graded_d1_games']}\n")
                out.write(f"- Paired D1 games: {report['paired_d1_games']}\n")
                for k in ("baseline_mae", "baseline_winner_accuracy", "paired_baseline_mae",
                          "paired_roster_mae", "paired_roster_minus_baseline_mae"):
                    if k in report:
                        out.write(f"- {k}: {report[k]}\n")
                out.write("\n")

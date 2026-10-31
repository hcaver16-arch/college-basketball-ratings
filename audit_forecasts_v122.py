"""Read-only validation of the two Courtside prospective forecast archives."""
from pathlib import Path
import json
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parent / "data" / "predictions"
SPORTS = ("mens-college-basketball", "womens-college-basketball")
REQUIRED = ("Game ID", "Game start UTC", "First forecast UTC",
            "Home ID", "Away ID", "Baseline home margin")

def inspect(sport):
    path = ROOT / sport / "first_forecasts.csv.gz"
    result = {"division": sport, "path": str(path.relative_to(ROOT.parent.parent)), "errors": [], "warnings": []}
    if not path.exists():
        result["errors"].append("Forecast archive missing")
        return result
    try:
        frame = pd.read_csv(path, compression="gzip", dtype={"Game ID": str, "Home ID": str, "Away ID": str})
    except Exception as exc:
        result["errors"].append(f"Archive unreadable: {exc}")
        return result
    result["rows"] = len(frame)
    missing = sorted(set(REQUIRED) - set(frame.columns))
    if missing:
        result["errors"].append("Required columns missing: " + ", ".join(missing))
        return result
    if frame.empty:
        result["warnings"].append("No prospective forecasts archived yet")
        return result
    ids = frame["Game ID"].astype("string").str.strip()
    result["duplicate_ids"] = int(ids.dropna().duplicated().sum())
    result["missing_ids"] = int((ids.isna() | (ids == "")).sum())
    starts = pd.to_datetime(frame["Game start UTC"], utc=True, errors="coerce")
    forecasts = pd.to_datetime(frame["First forecast UTC"], utc=True, errors="coerce")
    result["invalid_start_timestamps"] = int(starts.isna().sum())
    result["invalid_forecast_timestamps"] = int(forecasts.isna().sum())
    result["not_before_tip"] = int((forecasts.notna() & starts.notna() & (forecasts >= starts)).sum())
    margins = pd.to_numeric(frame["Baseline home margin"], errors="coerce")
    result["invalid_baseline_margins"] = int((~margins.notna()).sum())
    for field in ("Home ID", "Away ID"):
        values = frame[field].astype("string").str.strip()
        result["missing_" + field.lower().replace(" ", "_")] = int((values.isna() | (values == "")).sum())
    for field in ("duplicate_ids", "missing_ids", "invalid_start_timestamps",
                  "invalid_forecast_timestamps", "not_before_tip",
                  "invalid_baseline_margins", "missing_home_id", "missing_away_id"):
        if result[field]:
            result["errors"].append(f"{field}: {result[field]}")
    return result

def main():
    results = [inspect(sport) for sport in SPORTS]
    print(json.dumps({"audit": "V122 first-forecast integrity", "research_only": True,
                      "divisions": results}, indent=2))
    return 1 if any(item["errors"] for item in results) else 0

if __name__ == "__main__":
    sys.exit(main())

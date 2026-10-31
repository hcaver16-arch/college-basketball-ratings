"""Read-only opening-week data readiness checks for both college divisions."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import pandas as pd

SPORTS = ("mens-college-basketball", "womens-college-basketball")


def check(root: Path, now: datetime, max_age_hours: float = 48.0):
    findings = []
    for sport in SPORTS:
        issues, notes = [], []
        ratings = root / "data" / "ratings" / sport
        predictions = root / "data" / "predictions" / sport
        rstatus = ratings / "status.json"
        pstatus = predictions / "status.json"
        if not rstatus.is_file():
            issues.append("Ratings status missing")
        else:
            try:
                r = json.loads(rstatus.read_text())
                updated = pd.to_datetime(r.get("updated_utc"), utc=True, errors="coerce")
                if pd.isna(updated):
                    issues.append("Ratings timestamp missing or invalid")
                else:
                    age = (pd.Timestamp(now) - updated).total_seconds() / 3600
                    if age < -1 or age > max_age_hours:
                        issues.append(f"Ratings snapshot is stale/future ({age:.1f} hours)")
                if int(r.get("team_count", 0)) < 300:
                    issues.append("Ratings team count unexpectedly low")
            except (ValueError, TypeError, OSError) as exc:
                issues.append(f"Ratings status unreadable: {exc}")
        if not (ratings / "latest.csv.gz").is_file():
            issues.append("Latest ratings archive missing")
        if not pstatus.is_file():
            issues.append("Prediction status missing")
        else:
            try:
                p = json.loads(pstatus.read_text())
                updated = pd.to_datetime(p.get("updated_utc"), utc=True, errors="coerce")
                if pd.isna(updated):
                    issues.append("Prediction timestamp missing or invalid")
                else:
                    age = (pd.Timestamp(now) - updated).total_seconds() / 3600
                    if age < -1 or age > max_age_hours:
                        issues.append(f"Prediction refresh is stale/future ({age:.1f} hours)")
                archived = int(p.get("archived_forecasts", 0))
                if archived < 1:
                    issues.append("No archived first forecasts")
                notes.append(f"{archived} first forecasts; {p.get('evaluated_games', 0)} evaluated games")
            except (ValueError, TypeError, OSError) as exc:
                issues.append(f"Prediction status unreadable: {exc}")
        if not (predictions / "first_forecasts.csv.gz").is_file():
            issues.append("First forecasts archive missing")
        if not (root / "data" / "prospective" / "2026-27" / "forecasts.csv").is_file():
            issues.append("V97 prospective journal missing")
        findings.append({"division": sport, "ok": not issues, "issues": issues, "notes": notes})
    return findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--max-age-hours", type=float, default=48)
    parser.add_argument("--now-utc", help="ISO8601 timestamp for deterministic tests")
    args = parser.parse_args()
    now = pd.to_datetime(args.now_utc, utc=True).to_pydatetime() if args.now_utc else datetime.now(timezone.utc)
    result = check(Path(args.root), now, args.max_age_hours)
    print(json.dumps({"name": "Courtside V124 opening-week readiness", "checked_utc": now.isoformat(), "divisions": result}, indent=2))
    lines = ["## Opening-week readiness (V124)", "", f"Checked: {now.isoformat()}", ""]
    for item in result:
        lines.extend([f"### {item['division']}: {'PASS' if item['ok'] else 'ATTENTION'}",
                      *[f"- {n}" for n in item["notes"]],
                      *[f"- **Issue:** {n}" for n in item["issues"]], ""])
    import os
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("\n".join(lines) + "\n")
    raise SystemExit(1 if any(not item["ok"] for item in result) else 0)


if __name__ == "__main__":
    main()

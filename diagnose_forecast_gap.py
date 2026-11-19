"""Read-only diagnosis for an ESPN game missing a locked V97 forecast."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from prospective_archive_v97 import (
    FIELDS, SPORTS, load_official, newcomer_game, parse_dt, read_csv, scoreboard,
)

def diagnose(root, season, game_id, division, now, session=None):
    sport = SPORTS[0] if division == "mens" else SPORTS[1]
    folder = root / "data" / "prospective" / season
    records = read_csv(folder / "forecasts.csv", FIELDS)
    locked = [f for f in records if f["division"] == division
              and f["game_id"] == str(game_id) and f["model_id"] == "official_saved_v97"]
    today = now.astimezone(ZoneInfo("America/New_York")).date()
    games = {}
    fetch_errors = []
    for offset in range(-2, 3):
        day = today + timedelta(days=offset)
        try:
            games.update(scoreboard(sport, day, session=session))
        except Exception as exc:
            fetch_errors.append({"day": str(day), "error": str(exc)})
    game = games.get(str(game_id))
    ratings, rating_error = load_official(sport, root, now)
    report = {
        "game_id": str(game_id), "division": division, "checked_utc": now.isoformat(),
        "official_locked_forecast_count": len(locked),
        "locked_forecast_created_utc": [f["forecast_created_utc"] for f in locked],
        "schedule_found": game is not None, "scoreboard_fetch_errors": fetch_errors,
        "ratings_error": rating_error,
    }
    if not game:
        report["diagnosis"] = "GAME_NOT_FOUND_IN_ESPN_WINDOW"
        return report
    tip = parse_dt(game["game_start_utc"])
    report.update({
        "matchup": game["away_team"] + " @ " + game["home_team"],
        "home_id": game["home_id"], "away_id": game["away_id"],
        "tipoff_utc": game["game_start_utc"], "final": game["final"],
        "minutes_until_tipoff": round((tip - now).total_seconds() / 60, 1),
        "minimum_30min_lead_met": tip > now + timedelta(minutes=30),
        "within_42h_window": tip <= now + timedelta(hours=42),
        "v227_newcomer_hold": newcomer_game(game, season=season),
        "home_rating_present": bool(ratings and game["home_id"] in ratings["ratings"]),
        "away_rating_present": bool(ratings and game["away_id"] in ratings["ratings"]),
        "ratings_snapshot_utc": ratings["asof"].isoformat() if ratings else None,
    })
    if locked:
        report["diagnosis"] = "FORECAST_ALREADY_LOCKED_CHECK_HEALTH_REPORT_FRESHNESS"
    elif rating_error:
        report["diagnosis"] = "OFFICIAL_RATINGS_UNAVAILABLE"
    elif not report["home_rating_present"] or not report["away_rating_present"]:
        report["diagnosis"] = "MISSING_RATING_OR_ESPN_ID_MISMATCH"
    elif report["v227_newcomer_hold"]:
        report["diagnosis"] = "INTENTIONAL_V227_NEWCOMER_HOLD"
    elif game["final"] or not report["minimum_30min_lead_met"]:
        report["diagnosis"] = "TOO_LATE_DO_NOT_BACKFILL"
    elif not report["within_42h_window"]:
        report["diagnosis"] = "OUTSIDE_42H_WINDOW"
    elif ratings["asof"] > now or ratings["asof"] >= tip:
        report["diagnosis"] = "RATINGS_TIMESTAMP_INVALID_FOR_PREGAME"
    else:
        report["diagnosis"] = "ELIGIBLE_WITH_NO_LOCK_INSPECT_V97_RUN_AND_ESPN_SCHEDULE_TIMING"
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--season", default="2026-27")
    parser.add_argument("--division", choices=["mens", "womens"], default="mens")
    parser.add_argument("--game-id", default="401920517")
    args = parser.parse_args()
    report = diagnose(Path(args.root), args.season, args.game_id, args.division,
                      datetime.now(timezone.utc))
    print(json.dumps(report, indent=2))
    with open("diagnostic_report.json", "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
        file.write("\n")

if __name__ == "__main__":
    main()

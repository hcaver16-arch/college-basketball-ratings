"""Courtside V99: read-only prospective pipeline diagnostics.

Fetches ESPN schedules live, checks on-disk rating metadata and V97's
append-only archive; writes an independent health report. It never edits V97.
"""
from __future__ import annotations
import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

from prospective_archive_v97 import SPORTS, parse_dt, scoreboard, read_csv, FIELDS, RESULT_FIELDS, load_official

ET = ZoneInfo('America/New_York')
SEVERITY = {'ok': 0, 'info': 0, 'warning': 1, 'critical': 2}


def fetch_d1_membership(sport, session=None):
    """Use ESPN's D1 group-50 directory, matching the existing prediction archive.

    The saved power ratings include some non-D1 opponents. Ratings are therefore
    NOT proof of D1 membership. An incomplete directory must not be trusted.
    """
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/teams"
    response = (session or requests).get(
        url, params={"limit": 1000, "groups": "50"},
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    leagues = (payload.get("sports") or [{}])[0].get("leagues") or []
    teams = [
        item.get("team", item) for league in leagues
        for item in (league.get("teams") or [])
    ]
    ids = {str(team["id"]) for team in teams if team.get("id")}
    # An incomplete directory could wrongly classify genuine D1 contests
    # as non-D1. Treat it as unavailable instead of suppressing their alerts.
    if len(ids) < 200:
        raise RuntimeError(f"ESPN D1 directory incomplete ({len(ids)} team IDs)")
    return ids


def _finish_status(issues):
    return ("critical" if any(i["severity"] == "critical" for i in issues)
            else "warning" if any(i["severity"] == "warning" for i in issues)
            else "ok")


def check_division(
    root, season, division, now, games, forecasts, results, days=2,
    d1_ids=None, archive_asof=None, membership_error=None,
):
    """Check V97 integrity and *verified D1-v-D1* game readiness.

    Forecaster eligibility is not the same thing as D1 membership. Missing
    forecasts for rated D1-v-non-D1 games remain visible in diagnostics, but
    they must not masquerade as critical missing D1-v-D1 forecasts.
    """
    issues = []

    def issue(level, code, message, count=0, examples=None):
        issues.append({
            "severity": level, "code": code, "message": message,
            "count": count, "examples": (examples or [])[:8]
        })

    upcoming = [
        g for g in games.values()
        if not g["final"] and (parse_dt(g["game_start_utc"]) or now) > now
    ]
    imminent = [
        g for g in upcoming
        if parse_dt(g["game_start_utc"]) and
        parse_dt(g["game_start_utc"]) <= now + timedelta(hours=12)
    ]
    soon = [
        g for g in imminent
        if parse_dt(g["game_start_utc"]) <= now + timedelta(hours=3)
    ]
    completed = [
        g for g in games.values() if g["final"]
        and parse_dt(g["game_start_utc"])
        and parse_dt(g["game_start_utc"]) < now - timedelta(hours=8)
    ]
    division_forecasts = [
        f for f in forecasts
        if f["division"] == division and f["model_id"] == "official_saved_v97"
    ]
    forecast_map = {f["game_id"]: f for f in division_forecasts}
    result_ids = {
        r["game_id"] for r in results
        if r["division"] == division and r.get("status") == "Final"
    }

    sport = SPORTS[0] if division == "mens" else SPORTS[1]
    rating, error = load_official(sport, root, now)
    d1_known = d1_ids is not None
    d1_ids = {str(t) for t in d1_ids} if d1_known else set()
    d1_games = [
        g for g in imminent
        if g["home_id"] in d1_ids and g["away_id"] in d1_ids
    ]
    non_d1_games = [g for g in imminent if d1_known and g not in d1_games]
    if not d1_known:
        issue(
            "warning", "D1_DIRECTORY_UNAVAILABLE",
            "Cannot verify D1 matchup eligibility; forecast-coverage alerts are provisional",
            len(imminent), [str(membership_error or "D1 directory unavailable")],
        )

    # Distinguish a missed verified-D1 forecast from an unsupported mixed-
    # division opponent. Never manufacture a rating for the latter.
    missing = [g for g in d1_games if g["game_id"] not in forecast_map]
    urgent = [g for g in missing if g in soon]
    if urgent:
        issue(
            "critical", "MISSING_IMMINENT_D1_FORECASTS",
            f"{len(urgent)} verified D1-v-D1 games within three hours lack locked forecasts",
            len(urgent),
            [x["away_team"] + " @ " + x["home_team"] for x in urgent],
        )
    elif missing:
        issue(
            "warning", "MISSING_UPCOMING_D1_FORECASTS",
            f"{len(missing)} verified D1-v-D1 games within 12 hours lack locked forecasts",
            len(missing),
            [x["away_team"] + " @ " + x["home_team"] for x in missing],
        )

    # These V97 integrity rules apply to every archived forecast, regardless
    # of which division the opponents play in.
    bad = []
    for f in division_forecasts:
        p = parse_dt(f.get("forecast_created_utc"))
        t = parse_dt(f.get("game_start_utc"))
        snapshot = parse_dt(f.get("ratings_snapshot_utc"))
        if not (p and t and snapshot and snapshot <= p < t):
            bad.append(f.get("game_id"))
    if bad:
        issue(
            "critical", "INVALID_PREGAME_TIMESTAMPS",
            f"{len(bad)} official forecasts have invalid pre-tip timestamps",
            len(bad), bad,
        )
    counts = Counter(f["game_id"] for f in division_forecasts)
    duplicate = [k for k, v in counts.items() if v > 1]
    if duplicate:
        issue(
            "critical", "DUPLICATE_FORECASTS",
            "Official game IDs recorded more than once", len(duplicate), duplicate,
        )

    if error:
        # Unrated, non-D1 opponents should not make the official D1 monitor
        # critical, but missing ratings for verified D1 contests must.
        level = "critical" if d1_games else "warning" if imminent else "info"
        issue(level, "RATINGS_NOT_READY", error, len(d1_games))
    else:
        unrated = [
            g for g in d1_games
            if g["home_id"] not in rating["ratings"]
            or g["away_id"] not in rating["ratings"]
        ]
        if unrated:
            issue(
                "critical", "UNRATED_D1_TEAMS",
                f"{len(unrated)} imminent verified D1-v-D1 games have missing team ratings",
                len(unrated),
                [x["away_team"] + " @ " + x["home_team"] for x in unrated],
            )

    # V97 only settles finals during its own scheduled runs (12:15/18:15 UTC).
    # A newer live ESPN final is not overdue until at least one archive run
    # has occurred well after plausible game completion.
    archive_asof = parse_dt(archive_asof)
    unrecorded = [
        g for g in completed
        if g["game_id"] in forecast_map and g["game_id"] not in result_ids
    ]
    overdue = [
        g for g in unrecorded
        if archive_asof and archive_asof >= parse_dt(g["game_start_utc"]) + timedelta(hours=6)
    ]
    if overdue:
        issue(
            "warning", "MISSING_FINAL_RESULTS",
            f"{len(overdue)} ESPN-final games still lack results after a subsequent archive run",
            len(overdue), [x["game_id"] for x in overdue],
        )
    elif unrecorded and archive_asof is None:
        issue(
            "warning", "ARCHIVE_TIMESTAMP_UNAVAILABLE",
            "Cannot verify whether V97 ran after observed final games",
            len(unrecorded), [x["game_id"] for x in unrecorded],
        )
    # Do not create a warning for finals waiting for the next scheduled archive.
    pending = len(unrecorded) - len(overdue)

    if archive_asof and (now - archive_asof) > timedelta(hours=30):
        issue(
            "critical" if d1_games else "warning",
            "ARCHIVE_STALE",
            "The pregame/result archive has not refreshed for over 30 hours",
        )
    if not games:
        issue(
            "info", "NO_SCHEDULED_GAMES",
            "No games returned for the inspected dates; normal before the season",
        )
    return {
        "status": _finish_status(issues),
        "games_seen": len(games),
        "upcoming_12h": len(imminent),
        "upcoming_3h": len(soon),
        "verified_d1_upcoming_12h": len(d1_games),
        "excluded_non_d1_upcoming_12h": len(non_d1_games),
        "d1_classification_available": d1_known,
        "official_forecasts_total": len(division_forecasts),
        "final_results_total": sum(r["division"] == division for r in results),
        "results_waiting_for_next_archive": pending,
        "archive_as_of_utc": archive_asof.isoformat() if archive_asof else None,
        "issues": issues,
    }


def run(root, season, now, session=None):
    folder = root / "data" / "prospective" / season
    forecasts = read_csv(folder / "forecasts.csv", FIELDS)
    results = read_csv(folder / "results.csv", RESULT_FIELDS)
    try:
        archive_asof = json.loads((folder / "summary.json").read_text()).get("as_of_utc")
    except (OSError, ValueError, TypeError, AttributeError):
        archive_asof = None
    today = now.astimezone(ET).date()
    reports = {}
    fetch_issues = []
    for sport in SPORTS:
        division = "mens" if sport.startswith("mens") else "womens"
        combined = {}
        for offset in range(-3, 3):
            day = today + timedelta(days=offset)
            try:
                combined.update(scoreboard(sport, day, session=session))
            except Exception as exc:
                fetch_issues.append({
                    "division": division, "date": day.isoformat(), "error": str(exc)
                })
        d1_ids, membership_error = None, None
        try:
            d1_ids = fetch_d1_membership(sport, session=session)
        except Exception as exc:
            membership_error = str(exc)
        reports[division] = check_division(
            root, season, division, now, combined, forecasts, results,
            d1_ids=d1_ids, archive_asof=archive_asof,
            membership_error=membership_error,
        )
    if fetch_issues:
        status = "critical"
    elif any(r["status"] == "critical" for r in reports.values()):
        status = "critical"
    elif any(r["status"] == "warning" for r in reports.values()):
        status = "warning"
    else:
        status = "ok"
    result = {
        "version": 226, "season": season, "checked_at_utc": now.isoformat(timespec="seconds"),
        "status": status, "divisions": reports,
        "scoreboard_fetch_errors": fetch_issues,
        "notes": [
            "Read-only inspection; no forecasts, archived results, or model ratings are changed.",
            "D1 eligibility comes from the same ESPN group-50 team directory used by the first-forecast archive; rating presence alone is not D1 proof.",
            "Non-D1 matchups are excluded from D1 forecast critical alerts but remain counted.",
            "Finished games are not considered overdue until a subsequent V97 archive run had a reasonable opportunity to capture them.",
            "V97 must run independently; this workflow diagnoses but does not repair forecasts.",
        ],
    }
    destination = folder / "health_v99.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--season',default='2026-27');p.add_argument('--fail-on-critical',action='store_true');a=p.parse_args()
    x=run(Path(a.root),a.season,datetime.now(timezone.utc))
    print(json.dumps(x,indent=2))
    if a.fail_on_critical and x['status']=='critical':raise SystemExit(2)
if __name__=='__main__':main()

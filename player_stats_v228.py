"""V228: independently archived, verified 2026-27 ESPN individual box scores.

This collector NEVER writes power ratings, model forecasts, roster evidence,
or historical forecast files. D1 is established by ESPN's current group-50
team directory, not by presence in the ratings data.

Coverage is only relative to completed games actually discovered in ESPN's
group-50 daily scoreboard feed: it is NOT a guarantee that every NCAA game
was observed. National leaderboards are withheld while that observed coverage
is low. Source is ESPN's undocumented JSON API.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import json
import math
import os
from pathlib import Path
import tempfile

import pandas as pd
import requests

from player_stats_import import HEADERS, parse_boxscore, audit_team_scoring_source
from prospective_archive_v97 import SPORTS, event_data
ET = ZoneInfo("America/New_York")
from reliability_v99 import fetch_d1_membership

ROOT = Path(__file__).resolve().parent
SEASON = "2026-27"
FIRST_DAY = date(2026, 11, 1)
LAST_DAY = date(2027, 4, 12)
DIR = Path("data") / "player_stats_v228" / SEASON
GAMES_COLS = [
    "Division", "Game ID", "Game date ET", "Game start UTC",
    "Team ID", "Team", "Player ID", "Player", "Minutes", "Points",
    "Rebounds", "Assists", "Source",
]
COVER_COLS = [
    "Division", "Game ID", "Game date ET", "Game start UTC", "Team ID", "Team",
    "Team score", "Status", "Players parsed", "Checked at UTC", "Reason",
]
PLAYER_COLS = [
    "Division", "Team ID", "Team", "Player ID", "Player", "GP",
    "Minutes", "Points", "Rebounds", "Assists", "MPG", "PPG", "RPG", "APG",
]
READY_MIN_TEAM_GAMES = 30
READY_MIN_COVERAGE = 0.95
RECHECK_DAYS = 4
MAX_RETRY_OLD_GAMES = 100


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _read(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    raw = pd.read_csv(path, dtype={
        "Game ID": str, "Team ID": str, "Player ID": str,
    })
    if not set(columns).issubset(raw.columns):
        raise ValueError(f"Invalid previously archived player-data schema: {path}")
    return raw.reindex(columns=columns)


def _write(frame: pd.DataFrame, path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # The .tmp suffix must not inadvertently change gzip handling.
    fd, tmp = tempfile.mkstemp(prefix=path.stem + "-", dir=path.parent)
    os.close(fd)
    try:
        frame.reindex(columns=columns).to_csv(
            tmp, index=False, compression="gzip" if path.suffix == ".gz" else None
        )
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _valid_player_rows(rows, team_score):
    """Do not publish a team-game with incomplete or implausible box scores."""
    if not rows:
        return False, "No player rows found for this D1 team"
    ids = [str(x.get("Player ID") or "") for x in rows]
    if not all(ids) or len(set(ids)) != len(ids):
        return False, "Missing or duplicate player IDs in box score"
    if any(not str(r.get("Player") or "").strip() for r in rows):
        return False, "Missing player names in box score"
    for row in rows:
        for field in ("Minutes", "Points", "Rebounds", "Assists"):
            try:
                v = float(row[field])
            except (ValueError, TypeError, KeyError):
                return False, f"Invalid {field} in box score"
            if not math.isfinite(v) or v < 0:
                return False, f"Invalid {field} in box score"
    try:
        published_score = int(float(team_score)) if team_score is not None else None
    except (ValueError, TypeError, OverflowError):
        published_score = None
    if published_score is not None:
        total = sum(float(row["Points"]) for row in rows)
        # Team points may include a small number of technical-foul points
        # not attributed to an athlete. Large differences mean a partial feed.
        if abs(total - published_score) > 2:
            return False, f"Player points {total:g} do not reconcile with team score {published_score}"
    return True, ""


def summarize_players(game_rows: pd.DataFrame) -> pd.DataFrame:
    """Count observed appearances only; no DNPs or missing games as zero."""
    if game_rows.empty:
        return pd.DataFrame(columns=PLAYER_COLS)
    data = game_rows.copy()
    data["Player ID"] = data["Player ID"].astype(str)
    data["Team ID"] = data["Team ID"].astype(str)
    data["Game ID"] = data["Game ID"].astype(str)
    data = data.drop_duplicates(["Division", "Game ID", "Team ID", "Player ID"])
    for field in ("Minutes", "Points", "Rebounds", "Assists"):
        data[field] = pd.to_numeric(data[field], errors="coerce")
    data = data.dropna(subset=["Minutes", "Points", "Rebounds", "Assists"])
    if data.empty:
        return pd.DataFrame(columns=PLAYER_COLS)
    grouped = (data.groupby(["Division", "Team ID", "Player ID"], as_index=False)
        .agg({"Team": "last", "Player": "last", "Game ID": "nunique",
              "Minutes": "sum", "Points": "sum", "Rebounds": "sum", "Assists": "sum"})
        .rename(columns={"Game ID": "GP"}))
    for total, avg in (("Minutes", "MPG"), ("Points", "PPG"),
                       ("Rebounds", "RPG"), ("Assists", "APG")):
        grouped[avg] = (grouped[total] / grouped["GP"]).round(2)
        grouped[total] = grouped[total].round(2)
    return grouped[PLAYER_COLS].sort_values(
        ["PPG", "GP", "Player ID"], ascending=[False, False, True]
    ).reset_index(drop=True)


def coverage_summary(coverage: pd.DataFrame, athletes: pd.DataFrame, asof: datetime) -> dict:
    """The denominator is ESPN-discovered final *D1 team appearances*."""
    audited = coverage.drop_duplicates(["Division", "Game ID", "Team ID"], keep="last")
    total = len(audited)
    good = audited[audited["Status"].eq("verified")]
    successful = len(good)
    rate = round(successful / total, 4) if total else 0.0
    pending = audited[~audited["Status"].eq("verified")]
    explanations = pending["Reason"].fillna("").astype(str)
    source_mismatches = int(explanations.str.startswith("ESPN source mismatch:").sum())
    possible_parser_gaps = int(explanations.str.startswith("Possible parser omission:").sum())
    can_publish = (total >= READY_MIN_TEAM_GAMES and rate >= READY_MIN_COVERAGE)
    return {
        "as_of_utc": _iso(asof), "discovered_d1_team_game_boxscores": total,
        "verified_d1_team_game_boxscores": successful,
        "unverified_d1_team_game_boxscores": len(pending),
        "espn_source_score_mismatch_boxscores": source_mismatches,
        "possible_parser_scoring_gap_boxscores": possible_parser_gaps,
        "observed_boxscore_coverage": rate,
        "athletes_with_observed_games": len(athletes),
        "player_leaders_publishable": can_publish,
        "publication_minimum_observed_games": READY_MIN_TEAM_GAMES,
        "publication_minimum_coverage": READY_MIN_COVERAGE,
        "unverified_examples": [
            {"game_id": str(r["Game ID"]), "team": str(r["Team"]),
             "reason": str(r["Reason"])} for _, r in pending.head(12).iterrows()
        ],
        "coverage_scope": "ESPN-discovered final games with at least one verified D1 participant, NOT independently verified national schedule coverage",
        "sample_caution": "Observed per-game averages can be skewed by missing box scores, late corrections and players with very few games.",
    }


def _fetch_day(sport: str, day: date, session=None) -> dict:
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/scoreboard"
    response = (session or requests).get(
        url, params={"dates": day.strftime("%Y%m%d"), "groups": "50", "limit": 500},
        headers=HEADERS, timeout=30
    )
    response.raise_for_status()
    events = response.json().get("events")
    if not isinstance(events, list) or len(events) >= 500:
        raise ValueError(f"Truncated or invalid ESPN daily scoreboard {sport} {day}")
    return {g["game_id"]: g for e in events if (g := event_data(e))}


def _fetch_box(sport: str, game_id: str, session=None) -> dict:
    url = f"https://site.web.api.espn.com/apis/site/v2/sports/basketball/{sport}/summary"
    response = (session or requests).get(
        url, params={"event": game_id}, headers=HEADERS, timeout=30
    )
    response.raise_for_status()
    return response.json()


def _expected(game: dict, division: str, d1_ids: set[str]) -> list[dict]:
    if not game["final"]:
        return []
    # One game may contribute two verified team-game box scores.
    teams = [("home", game["home_id"], game["home_team"], game.get("home_score")),
             ("away", game["away_id"], game["away_team"], game.get("away_score"))]
    return [
        {"Division": division, "Game ID": str(game["game_id"]),
         "Game date ET": str(game["game_date_et"]),
         "Game start UTC": str(game["game_start_utc"]),
         "Team ID": str(tid), "Team": str(team),
         "Team score": score}
        for _, tid, team, score in teams if str(tid) in d1_ids
    ]


def _run_division(sport: str, root: Path, now: datetime, session=None,
                  d1_ids: set[str] | None = None) -> dict:
    division = "mens" if sport.startswith("mens-") else "womens"
    folder = root / DIR
    suffix = sport
    games_path = folder / f"{suffix}_games.csv.gz"
    coverage_path = folder / f"{suffix}_coverage.csv"
    players_path = folder / f"{suffix}_players.csv.gz"
    meta_path = folder / f"{suffix}_summary.json"
    existing_games = _read(games_path, GAMES_COLS)
    existing_cov = _read(coverage_path, COVER_COLS)

    prior_scan = None
    if meta_path.exists():
        try:
            old = json.loads(meta_path.read_text())
            prior_scan = date.fromisoformat(old["last_discovered_date_et"])
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            prior_scan = None
    # After a long outage this resumes from the last checked date; all days
    # in the gap are fetched, rather than silently skipping the outage.
    asof = min(now.astimezone(ET).date(), LAST_DAY)
    start = FIRST_DAY if prior_scan is None else max(FIRST_DAY, prior_scan - timedelta(days=RECHECK_DAYS))
    if start > asof:
        start = asof
    d1 = set(map(str, d1_ids)) if d1_ids is not None else fetch_d1_membership(sport, session=session)
    if len(d1) < 200:
        raise ValueError("Incomplete verified-D1 directory; player archive not updated")

    dates = [start + timedelta(days=n) for n in range((asof - start).days + 1)]
    discovered = {}
    # A scoreboard failure aborts without saving a false "success" watermark.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_fetch_day, sport, day, session): day for day in dates}
        for future in as_completed(futures):
            day = futures[future]
            try:
                discovered.update(future.result())
            except Exception as exc:
                raise RuntimeError(f"{sport} {day}: scoreboard discovery failed: {exc}") from exc

    expected = {}
    for game in discovered.values():
        for entry in _expected(game, division, d1):
            expected[(entry["Game ID"], entry["Team ID"])] = entry

    # Prior failed team-games are retried across all dates, not just the
    # recent discovery window; complete games are strictly append-only.
    known = {
        (str(r["Game ID"]), str(r["Team ID"])): r.to_dict()
        for _, r in existing_cov.iterrows()
    }
    for key, item in known.items():
        if item["Status"] != "verified" and key not in expected:
            expected[key] = {k: item.get(k) for k in COVER_COLS
                             if k in ("Division", "Game ID", "Game date ET",
                                      "Game start UTC", "Team ID", "Team", "Team score")}

    needed = {}
    # A metadata row alone is not proof its player rows survived a prior save.
    # Recollect an apparently "verified" box if the corresponding game lines
    # are missing, rather than exaggerating published player coverage.
    saved_player_keys = set(zip(
        existing_games["Game ID"].astype(str),
        existing_games["Team ID"].astype(str),
    ))
    for key, item in expected.items():
        if known.get(key, {}).get("Status") == "verified" and key in saved_player_keys:
            continue
        needed.setdefault(key[0], []).append(item)

    # Bound recurring retries without skipping newly completed fixtures.
    fresh_ids = {str(gid) for gid in discovered}
    fresh = [gid for gid in needed if gid in fresh_ids]
    older = [gid for gid in needed if gid not in fresh_ids][:MAX_RETRY_OLD_GAMES]
    work = fresh + older
    new_cov = []
    new_rows = []
    now_utc = _iso(now)
    def read_game(game_id):
        try:
            return _fetch_box(sport, game_id, session), ""
        except Exception as exc:
            return None, f"Summary unavailable: {str(exc)[:150]}"
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(read_game, gid): gid for gid in work}
        for future in as_completed(futures):
            gid = futures[future]
            payload, failure = future.result()
            for item in needed[gid]:
                if failure:
                    player_rows = []
                    reason = failure
                    valid = False
                else:
                    player_rows = parse_boxscore(payload, item["Team ID"], gid)
                    valid, reason = _valid_player_rows(player_rows, item["Team score"])
                    if not valid and reason.startswith("Player points "):
                        # Do not misdiagnose upstream ESPN source conflicts as
                        # dropped athletes, and never relax score reconciliation.
                        diagnosis = audit_team_scoring_source(
                            payload, item["Team ID"], gid,
                            player_rows, item["Team score"]
                        )
                        status = diagnosis["status"]
                        if status == "ESPN_RAW_PLAYER_TOTAL_DIFFERS_FROM_TEAM_FINAL":
                            reason = (
                                "ESPN source mismatch: raw athlete points "
                                f'{diagnosis["raw_espn_player_points"]:g} '
                                f'vs final team score {diagnosis["espn_final_team_points"]:g}; '
                                "no omitted scoring rows"
                            )
                        elif status == "PARSER_OR_ATHLETE_ROW_GAP":
                            reason = (
                                "Possible parser omission: parsed athlete points "
                                f'{diagnosis["parsed_player_points"]:g} '
                                f'vs ESPN raw athlete points {diagnosis["raw_espn_player_points"]:g}; '
                                f'{len(diagnosis["missing_positive_scoring_athlete_rows"])} '
                                "positive-point athletes unparsed"
                            )
                new_cov.append({
                    **item, "Status": "verified" if valid else "unverified",
                    "Players parsed": len(player_rows) if valid else 0,
                    "Checked at UTC": now_utc, "Reason": reason,
                })
                if valid:
                    new_rows.extend({
                        "Division": division, "Game ID": gid,
                        "Game date ET": item["Game date ET"],
                        "Game start UTC": item["Game start UTC"],
                        "Team ID": str(item["Team ID"]), "Team": str(item["Team"]),
                        "Player ID": str(p["Player ID"]), "Player": str(p["Player"]),
                        "Minutes": p["Minutes"], "Points": p["Points"],
                        "Rebounds": p["Rebounds"], "Assists": p["Assists"],
                        "Source": f"ESPN individual box score; {sport}; game {gid}",
                    } for p in player_rows)

    final_cov = pd.concat([existing_cov, pd.DataFrame(new_cov, columns=COVER_COLS)],
                          ignore_index=True).drop_duplicates(
                              ["Division", "Game ID", "Team ID"], keep="last")
    final_games = pd.concat([existing_games, pd.DataFrame(new_rows, columns=GAMES_COLS)],
                            ignore_index=True).drop_duplicates(
                                ["Division", "Game ID", "Team ID", "Player ID"], keep="first")
    # A previously verified game must never be downgraded or overwritten.
    athletes = summarize_players(final_games)
    report = coverage_summary(final_cov, athletes, now)
    report.update({
        "version": 228, "division": division, "season": SEASON,
        "last_discovered_date_et": str(asof),
        "verified_d1_team_directory_count": len(d1),
        "scoreboard_dates_fetched": len(dates),
        "summary_games_fetched": len(work),
        "last_collection_run_utc": now_utc,
        "source": "ESPN group-50 scoreboard and ESPN per-game individual boxscores",
        "historical_first_forecasts_modified": False,
    })
    _write(final_cov, coverage_path, COVER_COLS)
    _write(final_games, games_path, GAMES_COLS)
    _write(athletes, players_path, PLAYER_COLS)
    meta_path.write_text(json.dumps(report, indent=2) + "\n")
    return report


def run(root: Path = ROOT, now: datetime | None = None, session=None,
        d1_by_sport: dict | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    folder = root / DIR
    reports = {}
    errors = {}
    for sport in SPORTS:
        try:
            reports[sport] = _run_division(
                sport, root, now, session,
                (d1_by_sport or {}).get(sport),
            )
        except Exception as exc:
            errors[sport] = str(exc)
    # Saved successful division data is preserved if the other division
    # encounters a temporary ESPN feed error. Workflow fails visibly.
    summary = {
        "version": 228, "season": SEASON, "checked_at_utc": _iso(now),
        "divisions": reports, "errors": errors,
        "status": "error" if errors else
            "ready" if all(r["player_leaders_publishable"] for r in reports.values())
            else "collecting",
        "notes": [
            "Per-game rows and aggregated rates use only valid ESPN player boxscores, never inferred missing games.",
            "Coverage is computed against ESPN-discovered final D1-team games; unseen NCAA games cannot be counted.",
            "National-looking leaderboards remain unavailable until a substantial sample and 95% observed coverage.",
            "No rating engine, roster, first-forecast archive, or model probability has been changed.",
        ],
    }
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    if errors:
        raise RuntimeError(f"Player stats incomplete; {errors}")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(run(args.root), indent=2))


if __name__ == "__main__":
    main()

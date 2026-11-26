"""Courtside V260: independently archived, research-only multifactor shadow ratings.

Four separately inspectable, NON-FITTED hypotheses:
  1. Current on-court games: opponent-adjusted, preseason-anchored ridge-8 fit;
  2. Roster scoring-experience proxy: verified prior-year player points/40;
  3. Actual playing time: prior scoring experience weighted by observed minutes
     in the most recent verified completed team games;
  4. Head-coach continuity: SAME verified ESPN coach ID in two seasons.

An optional frozen V105 roster-retention index supplies context only.
These are deliberately conservative, untrained coefficients (not estimated
individual plus-minus, recruiting star ratings or coach quality). Missing
evidence does not become zero-quality talent.

Every first forecast is separately locked BEFORE scheduled tipoff and never
overwritten. Input files and source dates are captured; same-day results
are excluded from all shadow fits and lineup inputs. No production file is
read-write, no public ratings are altered and no official forecast is edited.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import json
import math

import pandas as pd
import numpy as np

from prospective_archive_v97 import (
    HEADERS, FIELDS as OFFICIAL_FIELDS, SPORTS, iso, load_official,
    parse_dt, read_csv, scoreboard, write_csv,
)
from prior_transition_research_v229 import anchored_ridge, normalize
from reliability_v99 import fetch_d1_membership
from shadow_coaches_v260 import coach_continuity

ROOT = Path(__file__).resolve().parent
SEASON = "2026-27"
MODEL_ID = "multifactor_shadow_v260"
OUT = Path("data") / "shadow_multifactor_v260" / SEASON
ET = ZoneInfo("America/New_York")
# Hypotheses are frozen on creation; changes require a NEW model ID.
COEFFICIENTS = {
    "ridge": 8.0,
    "home_advantage": 3.0,
    "prior_roster_v105_multiplier": .35,
    "talent_points_per_40_multiplier": .25,
    "minutes_role_multiplier": .18,
    "coach_continuity_magnitude": .20,
    "max_roster_continuity_points": .40,
    "max_talent_points": 1.25,
    "max_minutes_points": .85,
    "max_coach_points": .20,
}
FIELDS = [
    "season", "division", "game_id", "game_start_utc", "game_date_et",
    "home_id", "away_id", "home_team", "away_team", "neutral",
    "model_id", "forecast_created_utc", "official_ratings_snapshot_utc",
    "inputs_sha256", "home_shadow_power", "away_shadow_power",
    "home_anchored_on_court", "away_anchored_on_court",
    "home_roster_pts", "away_roster_pts", "home_talent_pts", "away_talent_pts",
    "home_minutes_pts", "away_minutes_pts", "home_coach_pts", "away_coach_pts",
    "home_talent_coverage", "away_talent_coverage",
    "home_minutes_coverage", "away_minutes_coverage",
    "home_coach_verified", "away_coach_verified",
    "home_verified_lineup_games", "away_verified_lineup_games",
    "predicted_home_margin", "model_status",
]
RESULT_FIELDS = [
    "season", "division", "game_id", "game_start_utc",
    "result_checked_utc", "home_score", "away_score",
    "actual_home_margin", "status",
]


def _read(path: Path, cols=None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=list(cols) if cols else [])
    return pd.read_csv(path, dtype={
        "Team ID": str, "Player ID": str, "Game ID": str,
        "Home ID": str, "Away ID": str, "team_id": str,
    }, low_memory=False)


def _number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _clip(value, limit):
    return float(np.clip(float(value), -limit, limit))


def prior_player_talent(roster: pd.DataFrame, prior_stats: pd.DataFrame) -> tuple[dict, float, dict]:
    """Historical PTS/40 is a SCORING EXPERIENCE PROXY, not recruit stars or talent rank.

    Only exact player IDs with one unique prior-season record are eligible.
    Both current and prior rosters are retrospective archived sources; they
    are not independently authenticated pregame eligibility snapshots.
    """
    need_roster = {"Team ID", "Player ID"}
    need_prior = {"Player ID", "Minutes", "Points"}
    if not need_roster.issubset(roster) or not need_prior.issubset(prior_stats):
        return {}, float("nan"), {"status": "missing_roster_or_prior_stats"}
    current = roster[["Team ID", "Player ID"]].copy()
    for col in ("Team ID", "Player ID"):
        current[col] = current[col].astype(str)
    current = current.drop_duplicates(["Team ID", "Player ID"])
    stats = prior_stats.copy()
    stats["Player ID"] = stats["Player ID"].astype(str)
    stats["Minutes"] = pd.to_numeric(stats["Minutes"], errors="coerce")
    stats["Points"] = pd.to_numeric(stats["Points"], errors="coerce")
    stats = stats[(stats["Minutes"] >= 100) & (stats["Points"] >= 0) &
                  stats["Minutes"].notna() & stats["Points"].notna()]
    # Multiple schools or separate prior-year records are not resolved by
    # max/scoring: those players are simply marked unverified.
    stats = stats[~stats["Player ID"].duplicated(keep=False)].copy()
    stats["prior_p40"] = (40*stats["Points"]/stats["Minutes"]).clip(0, 35)
    if len(stats) < 100:
        return {}, float("nan"), {"status": "incomplete_prior_player_pool", "usable": len(stats)}
    median = float(stats["prior_p40"].median())
    joined = current.merge(stats[["Player ID", "prior_p40"]], on="Player ID", how="left",
                           validate="many_to_one")
    info = {}
    for tid, group in joined.groupby("Team ID"):
        available = group.dropna(subset=["prior_p40"])
        n = len(group)
        info[str(tid)] = {
            "roster_players": n, "sourced_prior_players": len(available),
            "fraction": len(available)/n if n else 0.0,
            "roster_avg_prior_p40": float(available["prior_p40"].mean()) if len(available) else None,
            "player_priors": dict(zip(available["Player ID"].astype(str),
                                      available["prior_p40"].astype(float))),
        }
    return info, median, {
        "status": "available", "division_median_prior_p40": round(median, 4),
        "roster_teams": len(info), "unique_prior_players": len(stats),
        "definition": "previous-season player points/40, min 100 reported minutes; no opponent adjustment",
    }


def verified_recent_minutes(athletes: pd.DataFrame, coverage: pd.DataFrame,
                            now: datetime) -> dict:
    """Read only previously verified ESPN team-boxscores from earlier ET dates."""
    required_a = {"Game ID", "Game date ET", "Game start UTC", "Team ID",
                  "Player ID", "Minutes"}
    required_c = {"Game ID", "Team ID", "Game date ET", "Game start UTC",
                  "Checked at UTC", "Status"}
    if not required_a.issubset(athletes) or not required_c.issubset(coverage):
        return {}
    a, c = athletes.copy(), coverage.copy()
    for key in ("Game ID", "Team ID"):
        a[key] = a[key].astype(str)
        c[key] = c[key].astype(str)
    a["Player ID"] = a["Player ID"].astype(str)
    if a.duplicated(["Game ID", "Team ID", "Player ID"]).any():
        raise ValueError("Duplicate player-game lines in verified archive")
    if c.duplicated(["Game ID", "Team ID"]).any():
        raise ValueError("Duplicate team-game verification ledger")
    now = now.astimezone(timezone.utc)
    earlier_day = now.astimezone(ET).date()
    c["start"] = pd.to_datetime(c["Game start UTC"], utc=True, errors="coerce")
    c["checked"] = pd.to_datetime(c["Checked at UTC"], utc=True, errors="coerce")
    c["day"] = pd.to_datetime(c["Game date ET"], errors="coerce").dt.date
    c = c[(c["Status"].eq("verified")) & c["start"].notna() &
          c["checked"].notna() & (c["start"] < now) & (c["checked"] <= now) &
          (c["day"] < earlier_day) & c["day"].notna()]
    if c.empty:
        return {}
    v = c[["Game ID", "Team ID", "start"]]
    a = a.merge(v, on=["Game ID", "Team ID"], how="inner",
                validate="many_to_one")
    a["Minutes"] = pd.to_numeric(a["Minutes"], errors="coerce")
    if a["Minutes"].isna().any() or not a["Minutes"].between(0, 70).all():
        raise ValueError("Invalid minutes in verified player archive")
    if a.empty:
        return {}
    results = {}
    for team, rows in a.groupby("Team ID"):
        dates = (rows[["Game ID", "start"]]
                 .drop_duplicates("Game ID")
                 .sort_values(["start", "Game ID"]))
        last = set(dates.tail(5)["Game ID"].astype(str))
        recent = rows[rows["Game ID"].isin(last)]
        total = float(recent["Minutes"].sum())
        if total <= 0:
            continue
        grouped = recent.groupby("Player ID")["Minutes"].sum()
        results[str(team)] = {
            "verified_games": len(last),
            "observed_minutes": total,
            "player_minutes": {str(k): float(v) for k, v in grouped.items()},
            "latest_game_start_utc": dates.iloc[-1]["start"].isoformat(),
        }
    return results


def _v105_continuity(root: Path, sport: str) -> dict:
    path = root/"data"/"roster_experiment_v105"/f"{sport}_experimental_roster_sensitivity.csv"
    if not path.is_file():
        return {}
    rows = _read(path)
    required = {"team_id", "data_available", "confidence_weight", "origin_coverage_fraction",
                "illustrative_adjustment_points"}
    if not required.issubset(rows):
        return {}
    if rows["team_id"].astype(str).duplicated().any():
        raise ValueError("Duplicate V105 roster team IDs")
    result = {}
    for row in rows.to_dict("records"):
        if str(row["data_available"]).lower() != "true":
            continue
        points, confidence, origin = (_number(row.get(key)) for key in
                                      ("illustrative_adjustment_points", "confidence_weight",
                                       "origin_coverage_fraction"))
        if None in (points, confidence, origin) or confidence < .65 or origin < .65:
            continue
        result[str(row["team_id"])] = float(points)
    return result


def components_for_team(team_id: str, *, prior_rating: float,
                        anchored_rating: float, games_played: int,
                        talent_map: dict, median_prior_p40: float,
                        recent_minutes: dict, roster_v105: dict, coaches: dict) -> dict:
    """Explicit bounds prevent poor/unknown data from overpowering results."""
    tid = str(team_id)
    roster = talent_map.get(tid) or {}
    prior_players = roster.get("player_priors") or {}
    roster_fraction = float(roster.get("fraction") or 0)
    roster_mean = roster.get("roster_avg_prior_p40")
    has_talent = (math.isfinite(median_prior_p40) and
                  roster_mean is not None and len(prior_players) >= 5 and
                  roster_fraction >= .5)
    talent_pts = (_clip((float(roster_mean)-median_prior_p40) *
                        COEFFICIENTS["talent_points_per_40_multiplier"],
                        COEFFICIENTS["max_talent_points"]) * roster_fraction
                  if has_talent else 0.0)
    # Talent as a preseason adjustment fades when on-court evidence accumulates.
    talent_pts *= max(0.0, 1.0 - min(games_played/25.0, 1.0))
    recent = recent_minutes.get(tid) or {}
    minutes = recent.get("player_minutes") or {}
    recent_games = int(recent.get("verified_games") or 0)
    all_minutes = float(sum(minutes.values()))
    known = {pid: minutes[pid] for pid in minutes if pid in prior_players}
    known_minutes = float(sum(known.values()))
    minutes_fraction = known_minutes/all_minutes if all_minutes > 0 else 0.0
    minutes_pts = 0.0
    if (has_talent and recent_games >= 3 and
            minutes_fraction >= .6 and known_minutes > 0):
        usage_weighted_prior = sum(prior_players[pid]*mins for pid, mins in known.items())/known_minutes
        minutes_pts = _clip(
            (usage_weighted_prior-float(roster_mean)) *
            COEFFICIENTS["minutes_role_multiplier"],
            COEFFICIENTS["max_minutes_points"]) * min(recent_games/8, 1)
    v105 = roster_v105.get(tid)
    roster_pts = (_clip(v105*COEFFICIENTS["prior_roster_v105_multiplier"],
                         COEFFICIENTS["max_roster_continuity_points"]) *
                  max(0.0, 1.0 - min(games_played/20, 1))
                  if v105 is not None else 0.0)
    coach = coaches.get(tid)
    # This measures continuity vs transition ONLY (not coaching quality).
    coach_pts = ((COEFFICIENTS["coach_continuity_magnitude"] if coach["continuity"]
                  else -COEFFICIENTS["coach_continuity_magnitude"])
                 if coach else 0.0)
    total = float(anchored_rating+talent_pts+minutes_pts+roster_pts+coach_pts)
    if not math.isfinite(total):
        raise ValueError("Nonfinite experimental team rating")
    return {
        "team_id": tid, "prior_rating": round(float(prior_rating), 5),
        "anchored_on_court": round(float(anchored_rating), 5),
        "roster_pts": round(roster_pts, 5),
        "talent_pts": round(talent_pts, 5),
        "minutes_pts": round(minutes_pts, 5),
        "coach_pts": round(coach_pts, 5),
        "shadow_power": round(total, 5),
        "talent_coverage": round(roster_fraction, 5),
        "minutes_coverage": round(minutes_fraction, 5),
        "verified_lineup_games": recent_games,
        "coach_verified": bool(coach),
        "coach_id": str(coach["coach_id"]) if coach else "",
        "coach_name": str(coach["coach"]) if coach else "",
        "has_talent": bool(has_talent),
        "has_active_minutes_signal": bool(
            has_talent and recent_games >= 3 and minutes_fraction >= .6),
        "has_roster_coverage": v105 is not None,
        "old_v105_noncalibrated": v105 is not None,
    }


def input_sha256(root: Path, sport: str, coach_index: dict) -> tuple[str, dict]:
    paths = {
        "saved_ratings": root/"data"/"ratings"/sport/"latest.csv.gz",
        "saved_ratings_status": root/"data"/"ratings"/sport/"status.json",
        "current_scores": root/"data"/"ratings"/sport/"season_2026-27.csv.gz",
        "current_players": root/"data"/"player_stats_v228"/SEASON/f"{sport}_games.csv.gz",
        "current_player_coverage": root/"data"/"player_stats_v228"/SEASON/f"{sport}_coverage.csv",
        "current_roster": root/"data"/f"{sport}_current_rosters.csv.gz",
        "previous_stats": root/"data"/f"{sport}_previous_stats.csv.gz",
        "v105_roster": root/"data"/"roster_experiment_v105"/f"{sport}_experimental_roster_sensitivity.csv",
    }
    digests = {name: hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file()
               else "missing" for name, path in paths.items()}
    coaches_bytes = json.dumps(coach_index, sort_keys=True).encode()
    digests["verified_coaching_index"] = hashlib.sha256(coaches_bytes).hexdigest()
    return hashlib.sha256(json.dumps(digests, sort_keys=True).encode()).hexdigest(), digests


def build_snapshot(root: Path, sport: str, now: datetime, *,
                   d1_ids=None, coaches=None) -> tuple[dict, dict]:
    official, error = load_official(sport, root, now, max_age_hours=48)
    if error or official is None:
        raise ValueError(f"{sport}: dated official source snapshot unavailable: {error}")
    directory = (set(map(str, d1_ids)) if d1_ids is not None
                 else set(map(str, fetch_d1_membership(sport))))
    if len(directory) < 200:
        raise ValueError("Incomplete verified D1 membership")
    base = root/"data"/"ratings"/sport
    saved = _read(base/"latest.csv.gz")
    required = {"Team ID", "Preseason rating", "Games played", "Current power"}
    if not required.issubset(saved):
        raise ValueError(f"Missing saved preseason features {sorted(required-set(saved))}")
    saved["Team ID"] = saved["Team ID"].astype(str)
    if saved["Team ID"].duplicated().any():
        raise ValueError("Duplicate official team ID")
    saved["Preseason rating"] = pd.to_numeric(saved["Preseason rating"], errors="coerce")
    saved["Games played"] = pd.to_numeric(saved["Games played"], errors="coerce")
    saved = saved[saved["Team ID"].isin(directory)].dropna(
        subset=["Preseason rating", "Games played"])
    if len(saved) < 200:
        raise ValueError("Insufficient saved D1 preseason ratings")
    priors = dict(zip(saved["Team ID"], saved["Preseason rating"].astype(float)))
    starts = dict(zip(saved["Team ID"], saved["Games played"].astype(int)))
    current = normalize(_read(base/"season_2026-27.csv.gz"), "shadow season")
    # One full ET calendar-day embargo avoids possible same-day final or
    # delayed archive correction leaking into later games on the target day.
    earlier_day = now.astimezone(ET).date()
    current = current[current["Day"] < earlier_day]
    current = current[(current["Home ID"].isin(directory)) &
                      (current["Away ID"].isin(directory))].copy()
    anchored = anchored_ridge(priors, current, ridge=COEFFICIENTS["ridge"])
    data = root/"data"/"player_stats_v228"/SEASON
    observed = verified_recent_minutes(
        _read(data/f"{sport}_games.csv.gz"),
        _read(data/f"{sport}_coverage.csv"), now)
    roster, median, talent_audit = prior_player_talent(
        _read(root/"data"/f"{sport}_current_rosters.csv.gz"),
        _read(root/"data"/f"{sport}_previous_stats.csv.gz"))
    previous_v105 = _v105_continuity(root, sport)
    coaching = coaches or {}
    components = {
        tid: components_for_team(
            tid, prior_rating=priors[tid],
            anchored_rating=anchored.get(tid, priors[tid]),
            games_played=starts.get(tid, 0),
            talent_map=roster,
            median_prior_p40=median,
            recent_minutes=observed,
            roster_v105=previous_v105, coaches=coaching)
        for tid in sorted(priors)
    }
    digest, evidence_hashes = input_sha256(root, sport, coaching)
    summary = {
        "official_source_utc": iso(official["asof"]),
        "official_source_hash": official["sha256"],
        "model_id": MODEL_ID, "input_sha256": digest,
        "source_sha256": evidence_hashes,
        "on_court_archived_d1_finals_older_than_today_et": len(current),
        "last_game_day_used": str(current["Day"].max()) if len(current) else None,
        "roster_proxy_coverage": sum(v["has_talent"] for v in components.values()),
        "playing_time_proxy_coverage": sum(v["has_active_minutes_signal"]
                                           for v in components.values()),
        "coach_continuity_verified": sum(v["coach_verified"] for v in components.values()),
        "v105_research_roster_covered": sum(v["has_roster_coverage"] for v in components.values()),
        "all_verified_d1_rated_teams": len(components),
        "talent_audit": talent_audit,
        "warnings": [
            "The model combines anchored on-court results, documented prior scoring experience, verified current playing-time roles and explicitly sourced coach continuity.",
            "Prior points/40 do NOT measure comprehensive recruiting/star talent, individual defense, injury status or lineup-adjusted plus-minus.",
            "V105 continuity remains an old UNTRAINED heuristic; it does not confirm transfer eligibility.",
            "Coach continuity is NOT coaching ability; absent explicit head-coach role evidence there is zero coaching adjustment, flagged by coverage.",
            "Components are bounded fixed assumptions, not trained predictive coefficients.",
            "Source game results and player boxscores only from earlier ET dates; not same-day live games.",
        ],
    }
    return components, summary


def _safe_margin(prediction):
    x = _number(prediction)
    return x is not None and -150 <= x <= 150


def new_forecasts(events: dict, components: dict, existing: list,
                  now: datetime, division: str, summary: dict,
                  min_lead_minutes: int = 30) -> list:
    """Strictly one FIRST pretip forecast per (division, game, model_id)."""
    seen = {(f["division"], f["game_id"], f["model_id"]) for f in existing}
    created = []
    asof = parse_dt(summary["official_source_utc"])
    if asof is None or asof > now:
        raise ValueError("Undated or future-dated official source snapshot")
    from transition_research_v227 import newcomer_game
    for game in events.values():
        start = parse_dt(game.get("game_start_utc"))
        if (start is None or game.get("pregame") is not True or
                game.get("final") or
                start <= now + timedelta(minutes=max(30, min_lead_minutes)) or
                start > now + timedelta(hours=42) or
                asof >= start or newcomer_game(game, season=SEASON)):
            continue
        h, a = str(game["home_id"]), str(game["away_id"])
        if h not in components or a not in components:
            continue
        key = (division, str(game["game_id"]), MODEL_ID)
        if key in seen:
            continue
        hc, ac = components[h], components[a]
        edge = 0.0 if game["neutral"] else COEFFICIENTS["home_advantage"]
        margin = hc["shadow_power"] - ac["shadow_power"] + edge
        if not _safe_margin(margin):
            continue
        record = {
            "season": SEASON, "division": division,
            "game_id": str(game["game_id"]),
            "game_start_utc": game["game_start_utc"],
            "game_date_et": game["game_date_et"],
            "home_id": h, "away_id": a, "home_team": game["home_team"],
            "away_team": game["away_team"],
            "neutral": str(bool(game["neutral"])).lower(),
            "model_id": MODEL_ID,
            "forecast_created_utc": iso(now),
            "official_ratings_snapshot_utc": summary["official_source_utc"],
            "inputs_sha256": summary["input_sha256"],
            "home_shadow_power": hc["shadow_power"],
            "away_shadow_power": ac["shadow_power"],
            "home_anchored_on_court": hc["anchored_on_court"],
            "away_anchored_on_court": ac["anchored_on_court"],
            "home_roster_pts": hc["roster_pts"], "away_roster_pts": ac["roster_pts"],
            "home_talent_pts": hc["talent_pts"], "away_talent_pts": ac["talent_pts"],
            "home_minutes_pts": hc["minutes_pts"], "away_minutes_pts": ac["minutes_pts"],
            "home_coach_pts": hc["coach_pts"], "away_coach_pts": ac["coach_pts"],
            "home_talent_coverage": hc["talent_coverage"],
            "away_talent_coverage": ac["talent_coverage"],
            "home_minutes_coverage": hc["minutes_coverage"],
            "away_minutes_coverage": ac["minutes_coverage"],
            "home_coach_verified": str(hc["coach_verified"]).lower(),
            "away_coach_verified": str(ac["coach_verified"]).lower(),
            "home_verified_lineup_games": hc["verified_lineup_games"],
            "away_verified_lineup_games": ac["verified_lineup_games"],
            "predicted_home_margin": round(margin, 5),
            "model_status": "EXPERIMENTAL_UNTRAINED_NEVER_PRODUCTION",
        }
        created.append(record)
        seen.add(key)
    return created


def settle_forecasts(events: dict, first: list, prior_results: list,
                     now: datetime, division: str) -> list:
    have = {(r["division"], r["game_id"]) for r in prior_results}
    eligible = {(f["division"], f["game_id"]) for f in first}
    rows = []
    for game in events.values():
        key = (division, str(game["game_id"]))
        if (key in have or key not in eligible or not game.get("final") or
                parse_dt(game.get("game_start_utc")) is None or
                parse_dt(game["game_start_utc"]) >= now):
            continue
        hs, aws = _number(game.get("home_score")), _number(game.get("away_score"))
        if hs is None or aws is None or hs < 0 or aws < 0:
            continue
        rows.append({
            "season": SEASON, "division": division, "game_id": key[1],
            "game_start_utc": game["game_start_utc"],
            "result_checked_utc": iso(now),
            "home_score": int(hs), "away_score": int(aws),
            "actual_home_margin": int(hs-aws), "status": "Final",
        })
        have.add(key)
    return rows


def _metric(pairs):
    if not pairs:
        return {"games": 0, "mae": None, "signed_bias": None,
                "winner_accuracy": None}
    actual = np.array([float(x["actual"]) for x in pairs])
    pred = np.array([float(x["predicted"]) for x in pairs])
    correct = (np.sign(actual) == np.sign(pred))
    mask = (actual != 0) & (pred != 0)
    return {
        "games": len(pairs),
        "mae": round(float(np.abs(actual-pred).mean()), 4),
        "signed_bias": round(float((actual-pred).mean()), 4),
        "winner_accuracy": round(float(correct[mask].mean()), 4) if mask.any() else None,
    }


def evaluate(first: list, results: list, official: list) -> dict:
    finals = {(r["division"], r["game_id"]): r for r in results
              if r.get("status") == "Final"}
    off = {}
    for row in official:
        if row.get("model_id") != "official_saved_v97":
            continue
        start, created = parse_dt(row.get("game_start_utc")), parse_dt(row.get("forecast_created_utc"))
        if start is None or created is None or created >= start:
            continue
        key = (row["division"], row["game_id"])
        if key not in off:
            off[key] = row
    output = {}
    for div in ("mens", "womens"):
        own, paired_shadow, paired_official = [], [], []
        for row in first:
            if row["division"] != div or row["model_id"] != MODEL_ID:
                continue
            start = parse_dt(row["game_start_utc"])
            created = parse_dt(row["forecast_created_utc"])
            evidence = parse_dt(row["official_ratings_snapshot_utc"])
            if (not start or not created or not evidence or
                    not (evidence <= created < start)):
                continue
            final = finals.get((div, row["game_id"]))
            if final is None:
                continue
            pred = _number(row["predicted_home_margin"])
            actual = _number(final["actual_home_margin"])
            if pred is None or actual is None:
                continue
            own.append({"actual": actual, "predicted": pred})
            companion = off.get((div, row["game_id"]))
            if companion:
                other = _number(companion.get("predicted_home_margin"))
                if other is not None:
                    paired_shadow.append({"actual": actual, "predicted": pred})
                    paired_official.append({"actual": actual, "predicted": other})
        output[div] = {
            "shadow_all_locked_games": _metric(own),
            "same_game_paired_shadow": _metric(paired_shadow),
            "same_game_paired_official": _metric(paired_official),
            "informative_only_note": "Small early samples are observational; do not select model parameters on these results.",
        }
    return output


def run(root: Path = ROOT, now: datetime | None = None, *,
        season=SEASON, session=None, d1_lookup=None,
        coach_loader=None, scoreboard_reader=None) -> dict:
    if season != SEASON:
        raise ValueError("Unsupported shadow-model season")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    root = Path(root).resolve()
    folder = root/OUT
    folder.mkdir(parents=True, exist_ok=True)
    fpath, rpath = folder/"first_forecasts.csv", folder/"results.csv"
    first = read_csv(fpath, FIELDS)
    results = read_csv(rpath, RESULT_FIELDS)
    if len({(x["division"], x["game_id"], x["model_id"]) for x in first}) != len(first):
        raise ValueError("Duplicate locked first forecasts")
    if len({(x["division"], x["game_id"]) for x in results}) != len(results):
        raise ValueError("Duplicate completed shadow game results")
    feedback = {}
    from prospective_archive_v97 import report as _official_report
    for sport in SPORTS:
        division = "mens" if sport.startswith("mens-") else "womens"
        # Coach evidence failures affect coverage, not match availability;
        # two full-source fetches never fabricate an athlete/coach rating.
        if coach_loader:
            coaches, coach_status = coach_loader(sport, now)
        else:
            coaches, coach_status = coach_continuity(sport, now, session=session)
        ids = (d1_lookup(sport) if d1_lookup else None)
        snapshot, audit = build_snapshot(root, sport, now,
                                         d1_ids=ids, coaches=coaches)
        events = {}
        # All days must be returned successfully; incomplete ESPN lookups
        # must not be incorrectly presented as a complete successful refresh.
        day_et = now.astimezone(ET).date()
        for diff in (-2, -1, 0, 1, 2):
            day = day_et + timedelta(days=diff)
            rows = (scoreboard_reader(sport, day)
                    if scoreboard_reader else
                    scoreboard(sport, day, session=session))
            if not isinstance(rows, dict):
                raise ValueError(f"{sport} {day}: incomplete schedule")
            events.update(rows)
        additions = new_forecasts(events, snapshot, first, now, division, audit)
        first.extend(additions)
        finals = settle_forecasts(events, first, results, now, division)
        results.extend(finals)
        # Only this version's own output directory receives files.
        team_file = folder/f"{division}_latest_components.csv"
        pd.DataFrame(list(snapshot.values())).to_csv(team_file, index=False)
        feedback[division] = {
            **audit, "coaching_source": coach_status,
            "events_discovered": len(events),
            "new_immutable_forecasts": len(additions),
            "new_final_results": len(finals),
        }
    # Writes occur ONLY if both divisions' source/validation stages succeed.
    if not fpath.exists() or any(x["new_immutable_forecasts"] for x in feedback.values()):
        write_csv(fpath, first, FIELDS)
    if not rpath.exists() or any(x["new_final_results"] for x in feedback.values()):
        write_csv(rpath, results, RESULT_FIELDS)
    official_path = root/"data"/"prospective"/SEASON/"forecasts.csv"
    official = read_csv(official_path, OFFICIAL_FIELDS) if official_path.exists() else []
    summary = {
        "version": 260, "model_id": MODEL_ID, "mode": "INDEPENDENT_RESEARCH_SHADOW",
        "generated_utc": iso(now), "season": SEASON,
        "coefficients_untrained_and_frozen": COEFFICIENTS,
        "divisions": feedback,
        "total_immutable_forecasts": len(first), "total_final_results": len(results),
        "comparison_with_immutable_official_forecasts": evaluate(first, results, official),
        "limitations": [
            "No backfilled forecasts; model eligibility requires source snapshot before tipoff and at least 30 minutes forecast lead.",
            "Only opponent-adjusted team results, prior scoring experience, observed player minute shares and verified coach continuity are included; no observed individual defensive plus-minus or universal recruiting rankings.",
            "Model coefficient magnitudes are illustrative, not trained or calibrated. Historical nested validation is required before model selection.",
            "Current roster and player-identity sources may be incomplete or retrospectively updated, and ESPN coaching catalog may lack explicit head coach metadata. Coverage counters show unverified factors.",
            "Coach component is continuity vs change ONLY, not a coach-quality rating. Zero coverage means coaching remains disabled, not that coaches do not matter.",
            "Non-D1 newcomer forecasts remain excluded under the V227 safety rule.",
            "Saved results are strictly separate from model inputs and official production forecast archives.",
            "Do not compare independent MAEs without matching the SAME games and valid pretip timestamps.",
            "Original Courtside ratings, forecasts, website and January 1 checkpoint are unchanged.",
        ],
    }
    (folder/"summary.json").write_text(json.dumps(summary, indent=2, default=str)+"\n")
    print(json.dumps(summary, indent=2, default=str))
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--season", default=SEASON)
    args = p.parse_args()
    run(args.root, season=args.season)


if __name__ == "__main__":
    main()

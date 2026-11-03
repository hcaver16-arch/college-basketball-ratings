"""V227: evidence-gated D1 newcomer research; NEVER an official power rating.

Scope is current-season completed games against already-rated verified D1
opponents. The estimate is descriptive, unvalidated, and does NOT enter the
official rating engine, homepage model lines or immutable forecasts.

West Florida's 2026 transition and postseason ineligibility are independently
confirmed by UWF: https://news.uwf.edu/uwf-athletics-announces-move-to-ncaa-division-i-athletics-joins-atlantic-sun-conference-united-athletic-conference/
"""
from __future__ import annotations
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
DIVISIONS = ("mens-college-basketball", "womens-college-basketball")
WEST_FLORIDA_SOURCE = ("https://news.uwf.edu/"
    "uwf-athletics-announces-move-to-ncaa-division-i-athletics-joins-atlantic-sun-conference-united-athletic-conference/")
# Explicit independent evidence only: never infer all baseline-absent teams
# are NCAA newcomers, or that every reclassifying program is tournament-ineligible.
KNOWN_TRANSITIONS = {
    "2697": {
        "name": "West Florida Argonauts",
        "from_season": 2026,
        "full_ncaa_eligibility_year": 2029,
        "source": WEST_FLORIDA_SOURCE,
    }
}
MIN_OPPONENT_GAMES = 5
MIN_DISTINCT_D1_OPPONENTS = 3
RIDGE = 8.0
MAX_MARGIN = 40.0


def transitioning_ids(season="2026-27"):
    """Source-confirmed newcomers needing prospective model validation."""
    first = int(str(season).split("-")[0])
    return {
        tid for tid, evidence in KNOWN_TRANSITIONS.items()
        if int(evidence["from_season"]) <= first
    }


def ncaa_postseason_ineligible(season="2026-27"):
    """Only explicitly source-confirmed NCAA postseason exclusions."""
    first = int(str(season).split("-")[0])
    return {
        tid for tid, evidence in KNOWN_TRANSITIONS.items()
        if int(evidence["from_season"]) <= first < int(evidence["full_ncaa_eligibility_year"])
    }


def newcomer_game(game, verified_d1=None, season="2026-27"):
    """Restrict the hold on official projections to verified D1 games.

    This does not silently remove mixed-division games or broaden D1 membership.
    """
    home = str(game.get("Home ID", game.get("home_id", "")))
    away = str(game.get("Away ID", game.get("away_id", "")))
    if verified_d1 is not None and not (home in verified_d1 and away in verified_d1):
        return False
    return home in transitioning_ids(season) or away in transitioning_ids(season)


def _finite(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError, OverflowError):
        return None


def opponent_adjusted_research(
    candidate_id: str, season_games: pd.DataFrame,
    verified_d1: set[str], opponent_preseason: dict[str, float],
    asof: date,
):
    """Observations anchored to *opponents' preseason priors*, not postgame ratings.

    Derivation: margin(neutral) = power_home - power_away. Using fixed home
    advantage +3 and a cap of 40 matches the existing model's unit conventions.
    Weighted estimate = sum(candidate inferred powers)/(n+8); 0 is a
    regularization reference, NOT a validated newcomer prior.
    """
    candidate_id = str(candidate_id)
    observations = []
    opponents = set()
    game_ids = set()
    if not isinstance(season_games, pd.DataFrame) or season_games.empty:
        return {"eligible_games": 0, "distinct_opponents": 0, "research_estimate": None,
                "status": "INSUFFICIENT_COMPLETED_D1_GAMES"}
    columns = {"Game ID", "Date", "Home ID", "Away ID", "Home score", "Away score", "Venue", "Status"}
    if not columns.issubset(season_games.columns):
        return {"eligible_games": 0, "distinct_opponents": 0, "research_estimate": None,
                "status": "SEASON_RESULTS_SCHEMA_MISSING"}
    frame = season_games.copy()
    frame["Game ID"] = frame["Game ID"].astype(str)
    frame = frame.drop_duplicates("Game ID")
    for _, g in frame.iterrows():
        if g["Status"] != "Final": continue
        game_date = pd.to_datetime(g["Date"], errors="coerce")
        if pd.isna(game_date) or game_date.date() > asof: continue
        home, away = str(g["Home ID"]), str(g["Away ID"])
        if home == away or candidate_id not in (home, away): continue
        opponent = away if home == candidate_id else home
        if opponent not in verified_d1 or opponent == candidate_id: continue
        if str(g["Venue"]) not in ("Home", "Neutral"): continue
        hs, aws = _finite(g["Home score"]), _finite(g["Away score"])
        baseline = _finite(opponent_preseason.get(opponent))
        if hs is None or aws is None or baseline is None or hs < 0 or aws < 0: continue
        if (gid := str(g["Game ID"])) in game_ids: continue
        game_ids.add(gid)
        point_diff = max(-MAX_MARGIN, min(MAX_MARGIN, hs - aws))
        neutral_margin = point_diff - (0 if g["Venue"] == "Neutral" else 3.0)
        implied = baseline + neutral_margin if home == candidate_id else baseline - neutral_margin
        observations.append(implied)
        opponents.add(opponent)
    n = len(observations)
    sample_ok = n >= MIN_OPPONENT_GAMES and len(opponents) >= MIN_DISTINCT_D1_OPPONENTS
    return {
        "eligible_games": n, "distinct_opponents": len(opponents),
        "research_estimate": round(sum(observations) / (n + RIDGE), 2) if sample_ok else None,
        "observation_spread": (round(float(pd.Series(observations).std()), 2) if n > 1 else None),
        "status": "RESEARCH_ONLY_UNVALIDATED" if sample_ok else "INSUFFICIENT_COMPLETED_D1_GAMES",
    }


def research_report(root: Path, sport: str, d1_ids: set[str], asof: date):
    if sport not in DIVISIONS: raise ValueError("Invalid basketball division")
    rated_path = root / "data" / "ratings" / sport / "latest.csv.gz"
    season_path = root / "data" / "ratings" / sport / "season_2026-27.csv.gz"
    evidence_path = root / "data" / "d1_repair_v108" / f"{sport}_membership_evidence.csv"
    if not rated_path.exists() or not evidence_path.exists():
        raise FileNotFoundError("Ratings or source-vetted membership evidence missing")
    ratings = pd.read_csv(rated_path, dtype={"Team ID": str})
    evidence = pd.read_csv(evidence_path, dtype={"team_id": str})
    season = pd.read_csv(season_path, dtype={"Home ID": str, "Away ID": str, "Game ID": str}) if season_path.exists() else pd.DataFrame()
    if not {"Team ID", "Current power", "Preseason rating"}.issubset(ratings):
        raise ValueError("Required official ratings and preseason priors absent")
    ratings = ratings.drop_duplicates("Team ID", keep="first")
    official = set(ratings["Team ID"].astype(str))
    prior = dict(zip(ratings["Team ID"].astype(str), ratings["Preseason rating"]))
    evidencemap = evidence.set_index("team_id").to_dict("index") if "team_id" in evidence else {}
    # Source-confirmed candidate IDs are audited even if on-court only
    # processing added an early official rating (that isn't yet validated).
    missing = set(map(str, d1_ids)) - official
    candidates = sorted(missing | (transitioning_ids() & set(map(str, d1_ids))))
    out = []
    for tid in candidates:
        info = KNOWN_TRANSITIONS.get(tid)
        archival = evidencemap.get(tid, {})
        observed = opponent_adjusted_research(tid, season, set(map(str, d1_ids)), prior, asof)
        record = {
            "division": sport, "team_id": tid,
            "team": (info or {}).get("name") or str(archival.get("team") or tid),
            "d1_membership": "verified_ESPN_group_50",
            "source_confirmed_transition": bool(info),
            "in_current_saved_ratings": tid in official,
            "saved_baseline_missing": tid not in official or (bool(info) and str(archival.get("unavailable_rating")).lower()=="true"),
            "source_url": info["source"] if info else "",
            "ncaa_postseason_eligible": tid not in ncaa_postseason_ineligible(),
            "research_method": "opponent_preseason_plus_margin_ridge8",
            **observed,
            "official_forecast_eligible": False if info else None,
            "release_status": "MANUAL_HOLD_PENDING_VALIDATION" if info else "REQUIRES_MEMBERSHIP_REVIEW",
        }
        out.append(record)
    return pd.DataFrame(out), {
        "division": sport, "verified_d1_count": len(d1_ids),
        "missing_official_d1_ratings": len(missing),
        "source_confirmed_transition_count": sum(bool(row["source_confirmed_transition"]) for row in out),
        "research_only_estimate_count": sum(row["research_estimate"] is not None for row in out),
        "blocked_from_official_forecasts": [row["team"] for row in out if row["official_forecast_eligible"] is False],
        "status": "RESEARCH_ONLY_NO_MODEL_CHANGES",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "transition_research_v227")
    parser.add_argument("--asof", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    # Validate all remote directory data BEFORE replacing research outputs.
    from reliability_v99 import fetch_d1_membership
    results = {}
    reports = {}
    for sport in DIVISIONS:
        d1 = fetch_d1_membership(sport)
        results[sport], reports[sport] = research_report(args.root, sport, d1, args.asof)
    args.output.mkdir(parents=True, exist_ok=True)
    for sport, frame in results.items():
        frame.to_csv(args.output / f"{sport}.csv", index=False)
    summary = {
        "version": 227,
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "asof_date": str(args.asof),
        "notes": [
            "RESEARCH ONLY. No values are loaded into official rating snapshots, model lines, or forecast archives.",
            "Opponents anchored to preseason priors; 5 completed rated D1 games against 3 opponents before a provisional estimate is calculated.",
            "No D2-D1 calibration or prospective validation yet; a research estimate is not an official or betting-ready prediction.",
            "Explicitly reclassifying programs remain on a manual forecast hold until method evaluation and approval.",
        ],
        "divisions": reports,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

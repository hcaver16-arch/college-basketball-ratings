"""Courtside V250: retrospective production-rating response audit (research only).

V249 established that a morning snapshot dated D generally includes games
through Eastern date D-1. Compare dated snapshot D to D+1 only when both
teams' *saved* games played match the final-archive counts on either side of
a single game on D. These are observational associations, NOT proof of causal
game impacts or immutable timestamp-verified pre-tip predictions.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from datetime import timedelta
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research_rating_updates_v247 import ROOT, SPORTS, read, validate_games, validate_snapshots
from research_game_id_alignment_v249 import participation, game_lookup

HCA = 3.0
CAP = 40.0
LARGE_MOVEMENT = 0.05
GAME_COLUMNS = [
    "game_id", "eastern_game_day", "snapshot_before", "snapshot_after",
    "team_id", "team", "opponent_id", "opponent", "side", "venue",
    "team_power_before", "opponent_power_before", "prior_rating_before",
    "games_before", "opponent_games_before", "games_after",
    "preseason_weight_before", "preseason_weight_after",
    "rating_change", "prior_component", "on_court_component",
    "blend_component", "no_game_median_change", "change_minus_no_game_median",
    "expected_margin_proxy", "actual_margin", "capped_margin",
    "surprise_raw", "surprise_cap40", "blowout_over_40",
    "result", "phase", "opponent_strength", "surprise_band", "expected_role",
    "unusual_direction",
]


def cumulative_count(lookup: dict, team: str, day) -> int:
    return bisect_right(lookup.get(str(team), ([], []))[0], day)


def components(before: pd.Series, after: pd.Series) -> dict:
    w0 = float(before["Preseason weight"])
    w1 = float(after["Preseason weight"])
    prior0 = float(before["Preseason rating"])
    prior1 = float(after["Preseason rating"])
    court0 = float(before["On-court rating"]) if pd.notna(before["On-court rating"]) else 0.
    court1 = float(after["On-court rating"]) if pd.notna(after["On-court rating"]) else 0.
    result = {
        "rating_change": float(after["Current power"]-before["Current power"]),
        "prior_component": w0*(prior1-prior0),
        "on_court_component": (1-w0)*(court1-court0),
        "blend_component": (w1-w0)*(prior1-court1),
    }
    if abs(result["rating_change"]-sum(result[k] for k in (
        "prior_component", "on_court_component", "blend_component"))) > 0.12:
        raise ValueError("Production blend decomposition failed")
    return result


def phase(count: int) -> str:
    return "0-2 previous games" if count <= 2 else (
        "3-5 previous games" if count <= 5 else "6+ previous games")


def opponent_tier(power: float) -> str:
    return "below -10" if power < -10 else (
        "-10 to 0" if power < 0 else ("0 to 10" if power < 10 else "10+"))


def surprise_band(surprise: float) -> str:
    if surprise < -10:
        return "underperformed >10"
    if surprise < -3:
        return "underperformed 3-10"
    if surprise <= 3:
        return "within 3"
    if surprise <= 10:
        return "outperformed 3-10"
    return "outperformed >10"


def expected_role(margin: float) -> str:
    return "expected underdog" if margin < -8 else (
        "expected favorite" if margin > 8 else "near even")


def validated_count(row: pd.Series, lookup: dict, team: str, day) -> bool:
    return int(row["Games played"]) == cumulative_count(lookup, team, day)


def audit(snaps: pd.DataFrame, finals: pd.DataFrame):
    """Only games isolated between two adjacent, V249-consistent snapshots."""
    snaps = validate_snapshots(snaps)
    finals = validate_games(finals) if "capped_margin" not in finals.columns else finals
    dates = set(snaps["Snapshot date"].unique())
    lookup = game_lookup(participation(finals))
    by_date = {day: sub.set_index("Team ID", verify_integrity=True)
               for day, sub in snaps.groupby("Snapshot date")}
    results = []
    coverage = {"archived_final_games": len(finals), "eligible_games": 0,
                "missing_adjacent_daily_snapshot": 0,
                "missing_team_snapshot": 0, "non_isolated_team_game": 0,
                "snapshot_archive_count_inconsistent": 0,
                "same_day_games_passing_all_checks": 0}
    for day, group in finals.groupby("Date", sort=True):
        next_day = day+timedelta(days=1)
        if day not in dates or next_day not in dates:
            coverage["missing_adjacent_daily_snapshot"] += len(group)
            continue
        pre = by_date[day]
        post = by_date[next_day]
        previous_final_day = day-timedelta(days=1)
        # The baseline is descriptive: median team rating drift among teams
        # that had zero archive games and unchanged saved game counts.
        controls = []
        for team in pre.index.intersection(post.index):
            b, a = pre.loc[team], post.loc[team]
            if (validated_count(b, lookup, str(team), previous_final_day) and
                    validated_count(a, lookup, str(team), day) and
                    int(a["Games played"]) == int(b["Games played"])):
                controls.append(float(a["Current power"]-b["Current power"]))
        control = float(np.median(controls)) if controls else 0.0
        for _, game in group.iterrows():
            home, away = str(game["Home ID"]), str(game["Away ID"])
            if home not in pre.index or away not in pre.index or (
                    home not in post.index or away not in post.index):
                coverage["missing_team_snapshot"] += 1
                continue
            before_h, before_a = pre.loc[home], pre.loc[away]
            after_h, after_a = post.loc[home], post.loc[away]
            isolated = all(
                cumulative_count(lookup, team, day)-cumulative_count(
                    lookup, team, previous_final_day) == 1
                for team in (home, away))
            if not isolated:
                coverage["non_isolated_team_game"] += 1
                continue
            counts_ok = all(
                validated_count(b, lookup, t, previous_final_day) and
                validated_count(a, lookup, t, day) and
                int(a["Games played"])-int(b["Games played"]) == 1
                for t, b, a in (
                    (home, before_h, after_h), (away, before_a, after_a)))
            if not counts_ok:
                coverage["snapshot_archive_count_inconsistent"] += 1
                continue
            expected_home = float(before_h["Current power"] -
                                  before_a["Current power"] +
                                  (HCA if game["Venue"] == "Home" else 0.))
            raw_home = float(game["Home score"]-game["Away score"])
            capped_home = float(np.clip(raw_home, -CAP, CAP))
            for team, opp, side, b, a, ob in (
                (home, away, "home", before_h, after_h, before_a),
                (away, home, "away", before_a, after_a, before_h)):
                sign = 1 if side == "home" else -1
                raw = raw_home*sign
                capped = capped_home*sign
                expected = expected_home*sign
                movement = components(b, a)
                movement["game_id"] = str(game["Game ID"])
                movement["eastern_game_day"] = str(day)
                movement["snapshot_before"] = str(day)
                movement["snapshot_after"] = str(next_day)
                movement["team_id"] = team
                movement["team"] = str(b.get("Team", team))
                movement["opponent_id"] = opp
                movement["opponent"] = str(ob.get("Team", opp))
                movement["side"] = side
                movement["venue"] = str(game["Venue"])
                movement["team_power_before"] = float(b["Current power"])
                movement["opponent_power_before"] = float(ob["Current power"])
                movement["prior_rating_before"] = float(b["Preseason rating"])
                movement["games_before"] = int(b["Games played"])
                movement["opponent_games_before"] = int(ob["Games played"])
                movement["games_after"] = int(a["Games played"])
                movement["preseason_weight_before"] = float(b["Preseason weight"])
                movement["preseason_weight_after"] = float(a["Preseason weight"])
                movement["no_game_median_change"] = control
                movement["change_minus_no_game_median"] = movement["rating_change"]-control
                movement["expected_margin_proxy"] = expected
                movement["actual_margin"] = raw
                movement["capped_margin"] = capped
                movement["surprise_raw"] = raw-expected
                movement["surprise_cap40"] = capped-expected
                movement["blowout_over_40"] = abs(raw) > CAP
                movement["result"] = "win" if raw > 0 else ("loss" if raw < 0 else "tie")
                movement["phase"] = phase(int(b["Games played"]))
                movement["opponent_strength"] = opponent_tier(
                    float(ob["Current power"]))
                movement["surprise_band"] = surprise_band(capped-expected)
                movement["expected_role"] = expected_role(expected)
                movement["unusual_direction"] = (
                    "win_and_rating_fell" if raw > 0 and
                    movement["rating_change"] < -LARGE_MOVEMENT else
                    ("loss_and_rating_rose" if raw < 0 and
                     movement["rating_change"] > LARGE_MOVEMENT else "none"))
                results.append(movement)
            coverage["eligible_games"] += 1
    evidence = pd.DataFrame(results, columns=GAME_COLUMNS)
    coverage["same_day_games_passing_all_checks"] = coverage["eligible_games"]
    if coverage["eligible_games"]*2 != len(evidence):
        raise ValueError("Expected exactly two team observations per game")
    if sum(coverage[k] for k in (
        "eligible_games", "missing_adjacent_daily_snapshot",
        "missing_team_snapshot", "non_isolated_team_game",
        "snapshot_archive_count_inconsistent")) != coverage["archived_final_games"]:
        raise ValueError("Game-level coverage accounting failed")
    return evidence, coverage


def describe(group: pd.DataFrame):
    return {"team_game_observations": int(len(group)),
            "mean_rating_change": round(float(group["rating_change"].mean()), 5),
            "median_rating_change": round(float(group["rating_change"].median()), 5),
            "mean_control_adjusted_change": round(float(
                group["change_minus_no_game_median"].mean()), 5),
            "mean_margin_surprise_cap40": round(float(
                group["surprise_cap40"].mean()), 4),
            "mean_abs_on_court_component": round(float(
                group["on_court_component"].abs().mean()), 5),
            "mean_abs_blend_component": round(float(
                group["blend_component"].abs().mean()), 5),
            "win_and_rating_fell": int(group["unusual_direction"].eq(
                "win_and_rating_fell").sum()),
            "loss_and_rating_rose": int(group["unusual_direction"].eq(
                "loss_and_rating_rose").sum())}


def grouped(evidence: pd.DataFrame, names: list[str]) -> list[dict]:
    if evidence.empty:
        return []
    rows = []
    for key, sub in evidence.groupby(names, dropna=False, observed=True):
        dims = (key,) if len(names) == 1 else key
        rows.append({**dict(zip(names, dims)), **describe(sub)})
    return rows


def summarize(evidence: pd.DataFrame, coverage: dict):
    result = {"coverage": coverage, "total_team_game_observations": len(evidence),
              "status": "DESCRIPTIVE_OBSERVATIONAL_ONLY",
              "threshold_for_unusual_rating_move": LARGE_MOVEMENT}
    if len(evidence):
        result["overall"] = describe(evidence)
        result["by_result"] = grouped(evidence, ["result"])
        result["by_previous_games_and_result"] = grouped(
            evidence, ["phase", "result"])
        result["by_opponent_strength_and_result"] = grouped(
            evidence, ["opponent_strength", "result"])
        result["by_surprise_and_result"] = grouped(
            evidence, ["surprise_band", "result"])
        result["by_expected_role_and_result"] = grouped(
            evidence, ["expected_role", "result"])
        result["by_blowout_and_result"] = grouped(
            evidence, ["blowout_over_40", "result"])
    else:
        result["overall"] = None
        for key in ("by_result", "by_previous_games_and_result",
                    "by_opponent_strength_and_result", "by_surprise_and_result",
                    "by_expected_role_and_result", "by_blowout_and_result"):
            result[key] = []
    result["limitations"] = [
        "V249-consistent snapshot date D is assumed a morning pregame refresh, but its actual historical execution timestamp is unavailable; these are not verified archived pre-tip forecasts.",
        "The archived final-game score may have been corrected after the snapshot; final-state archive is not a dated historical ingestion log.",
        "A game is selected only when it is the one final archived game for EACH team on the Eastern game date, and saved game counts match cumulative archive through D-1 and D.",
        "Game-linked rating movement is ASSOCIATION, not the isolated causal effect of that game: all teams are simultaneously refitted.",
        "The expected score margin is only a +3 home-court proxy from saved team powers, not Courtside's archived official forecast.",
        "Opponent quality is a prior saved power-rating value, not an independent external schedule strength estimate.",
        "No historical or prospective model parameter is tuned or promoted.",
        "Study contains non-D1 teams where they appear in the production rating snapshot; it is not a validated D1 ranking.",
    ]
    return result


def run(root: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    result = {"version": 250, "status": "RESEARCH_ONLY_NOT_DEPLOYED",
              "production_changed": False, "divisions": {}}
    for division in SPORTS:
        base = root/"data/ratings"/division
        snapshots = read(base/"history.csv.gz")
        games = read(base/"season_2026-27.csv.gz")
        evidence, coverage = audit(snapshots, games)
        result["divisions"][division] = summarize(evidence, coverage)
        evidence.to_csv(out/f"{division}_linked_rating_responses.csv", index=False)
        evidence[evidence["unusual_direction"].ne("none")].to_csv(
            out/f"{division}_unexpected_direction_cases.csv", index=False)
        if len(evidence):
            team_summary = (
                evidence.groupby(["team_id", "team"], as_index=False)
                .agg(games_observed=("game_id", "nunique"),
                     average_opponent_power=("opponent_power_before", "mean"),
                     average_margin_surprise=("surprise_cap40", "mean"),
                     average_rating_change=("rating_change", "mean"),
                     total_observed_rating_change=("rating_change", "sum"),
                     win_rating_declines=("unusual_direction", lambda x: int(
                         x.eq("win_and_rating_fell").sum())),
                     loss_rating_increases=("unusual_direction", lambda x: int(
                         x.eq("loss_and_rating_rose").sum()))))
            team_summary.sort_values(
                ["games_observed", "total_observed_rating_change"],
                ascending=[False, False]).to_csv(
                    out/f"{division}_team_cases.csv", index=False)
    (out/"summary.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=ROOT/"data/research_rating_response_v250")
    args = parser.parse_args()
    run(args.root.resolve(), args.out.resolve())

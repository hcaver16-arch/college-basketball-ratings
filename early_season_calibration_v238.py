"""V238: read-only early-season basketball rating calibration audit.

No production model or published forecast changes. Uses ONLY saved results:
previous-season scores become the frozen prior; for each 2026-27 game day D,
all candidate fits use current-season finals dated STRICTLY BEFORE D.
This is a retrospective day-before replay, not a true saved pre-tip forecast.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from prior_transition_research_v229 import (
    SPORTS, HOME_ADVANTAGE, CAP, anchored_ridge, historical_prior,
    legacy_replay, metrics, normalize,
)
from rating_engine import blending_weight

ROOT = Path(__file__).resolve().parent
MODELS = ("prior_only", "legacy_replay", "anchored_ridge4",
          "anchored_ridge8", "anchored_ridge16")
MIN_INFORMATIVE = 100


def _power(prior: dict[str, float], games: pd.DataFrame) -> dict:
    """Fit the fixed hypotheses, never fitting or selecting their coefficients."""
    legacy, _ = legacy_replay(prior, games)
    return {
        "prior_only": dict(prior),
        "legacy_replay": legacy,
        "anchored_ridge4": anchored_ridge(prior, games, ridge=4.0),
        "anchored_ridge8": anchored_ridge(prior, games, ridge=8.0),
        "anchored_ridge16": anchored_ridge(prior, games, ridge=16.0),
    }


def _counts(frame: pd.DataFrame) -> dict[str, int]:
    if frame.empty:
        return {}
    return pd.concat((frame["Home ID"], frame["Away ID"])).astype(str).value_counts().to_dict()


def states_by_day(prior: dict, current: pd.DataFrame) -> dict:
    """Build before/after views; never use a target day's scores to predict it."""
    state = _power(prior, current.iloc[:0])
    result = {}
    for day in sorted(current["Day"].unique()):
        prior_state = state
        earlier = current[current["Day"] < day]
        through = current[current["Day"] <= day]
        state = _power(prior, through)
        assert earlier.empty or earlier["Day"].max() < day
        result[day] = {
            "before": prior_state,
            "after": state,
            "latest_training_day": str(earlier["Day"].max()) if not earlier.empty else None,
            "games_before": len(earlier),
            "counts_before": _counts(earlier),
            "counts_on_day": _counts(current[current["Day"] == day]),
        }
    return result


def _predict(ratings, home, away, venue):
    if home not in ratings or away not in ratings:
        return None
    a, b = float(ratings[home]), float(ratings[away])
    if not np.isfinite(a) or not np.isfinite(b):
        return None
    return a - b + (0.0 if venue == "Neutral" else HOME_ADVANTAGE)


def compare_chronologically(prior: dict, current: pd.DataFrame,
                            d1_ids: set[str], asof: date):
    """All models on identical verified D1 fixtures, prior to each game DAY.

    All games on day D are held out even if an earlier game finished first.
    Coefficients are hypotheses, not re-tuned on these same results.
    """
    if len(d1_ids) < 200:
        raise ValueError("Incomplete ESPN current D1 membership; refusing comparison")
    current = current[(current["Day"] >= date(2026, 11, 1)) &
                      (current["Day"] <= asof)].copy()
    states = states_by_day(prior, current)
    rows = []
    for day, day_games in current.groupby("Day", sort=True):
        state = states[day]
        for game in day_games.to_dict("records"):
            h, a = str(game["Home ID"]), str(game["Away ID"])
            if h not in d1_ids or a not in d1_ids or h not in prior or a not in prior:
                continue
            record = {
                "game_id": str(game["Game ID"]), "day": str(day),
                "home_id": h, "away_id": a,
                "home_team": str(game["Home"]), "away_team": str(game["Away"]),
                "actual_margin": float(game["Home score"] - game["Away score"]),
                "neutral": game["Venue"] == "Neutral",
                "latest_training_day": state["latest_training_day"],
                "home_gp_before": int(state["counts_before"].get(h, 0)),
                "away_gp_before": int(state["counts_before"].get(a, 0)),
            }
            for key in MODELS:
                record[key] = _predict(state["before"][key], h, a, game["Venue"])
            if all(record[key] is not None for key in MODELS):
                assert record["latest_training_day"] is None or record["latest_training_day"] < record["day"]
                rows.append(record)
    matched = pd.DataFrame(rows)
    if not matched.empty:
        matched = matched.sort_values(["day", "game_id"]).reset_index(drop=True)
    data = matched.to_dict("records")
    scored = {name: metrics(data, name) for name in MODELS}
    if matched.empty:
        informative = matched
    else:
        alternatives = matched[[m for m in MODELS if m != "prior_only"]]
        informative = matched[(alternatives.max(axis=1) - alternatives.min(axis=1)) > 0.05]
    segments = {}
    if not matched.empty:
        for name, mask in {
            "both_0_to_2_games": (matched["home_gp_before"] <= 2) & (matched["away_gp_before"] <= 2),
            "either_3_plus_games": (matched["home_gp_before"] >= 3) | (matched["away_gp_before"] >= 3),
        }.items():
            segment = matched.loc[mask].to_dict("records")
            segments[name] = {model: metrics(segment, model) for model in MODELS}
    summary = {
        "matched_d1_games": len(matched),
        "informative_model_disagreement_games": len(informative),
        "informative_definition": "range of four non-prior-only candidates > 0.05 projected-margin points",
        "metrics_same_games": scored,
        "metrics_informative_only": {name: metrics(informative.to_dict("records"), name) for name in MODELS},
        "segments_same_games": segments,
        "first_replayed_day": str(min(states)) if states else None,
        "last_replayed_day": str(max(states)) if states else None,
        "max_latest_training_day": max(
            (s["latest_training_day"] for s in states.values()
             if s["latest_training_day"] is not None), default=None),
        "status": ("NO_MATCHED_GAMES" if matched.empty else
                   "EXPLORATORY_INSUFFICIENT_INFORMATIVE_SAMPLE"
                   if len(informative) < MIN_INFORMATIVE else
                   "EXPLORATORY_ONLY_NOT_INDEPENDENT_PROSPECTIVE_EVIDENCE"),
    }
    return matched, summary, states


def strong_win_diagnostics(prior: dict, current: pd.DataFrame,
                           states: dict, d1_ids: set[str]) -> pd.DataFrame:
    """Explain post-day changes following wins by 25+; not a causal attribution."""
    rows = []
    for game in current.to_dict("records"):
        day = game["Day"]
        if day not in states:
            continue
        h, a = str(game["Home ID"]), str(game["Away ID"])
        margin = float(game["Home score"] - game["Away score"])
        for team, opponent, team_margin, location in (
            (h, a, margin, "Home" if game["Venue"] != "Neutral" else "Neutral"),
            (a, h, -margin, "Away" if game["Venue"] != "Neutral" else "Neutral"),
        ):
            if team_margin < 25 or team not in d1_ids or team not in prior:
                continue
            state = states[day]
            before, after = state["before"], state["after"]
            if any(team not in before[m] or team not in after[m] for m in MODELS):
                continue
            legacy_change = after["legacy_replay"][team] - before["legacy_replay"][team]
            anchored_change = after["anchored_ridge8"][team] - before["anchored_ridge8"][team]
            expected = None
            if opponent in prior:
                expected = (float(prior[team]) - float(prior[opponent]) +
                            (HOME_ADVANTAGE if location == "Home" else
                             -HOME_ADVANTAGE if location == "Away" else 0.0))
            rows.append({
                "day": str(day), "game_id": str(game["Game ID"]),
                "team_id": team, "team": str(game["Home"] if team == h else game["Away"]),
                "opponent_id": opponent,
                "opponent": str(game["Away"] if team == h else game["Home"]),
                "opponent_verified_current_d1": opponent in d1_ids,
                "location": location, "winning_margin": team_margin,
                "capped_winning_margin": min(float(CAP), team_margin),
                "prior_team_power": float(prior[team]),
                "opponent_prior_power": float(prior[opponent]) if opponent in prior else None,
                "prior_expected_winning_margin": expected,
                "legacy_power_before_day": round(before["legacy_replay"][team], 4),
                "legacy_power_after_day": round(after["legacy_replay"][team], 4),
                "legacy_change_after_day": round(legacy_change, 4),
                "anchored8_change_after_day": round(anchored_change, 4),
                "legacy_dropped_after_win": bool(legacy_change < -0.025),
                "games_before_day": int(state["counts_before"].get(team, 0)),
                "team_finals_on_day": int(state["counts_on_day"].get(team, 0)),
                "legacy_blend_weight_after_day": round(
                    float(blending_weight(int(state["counts_before"].get(team, 0) +
                                              state["counts_on_day"].get(team, 0)))), 3),
            })
    return pd.DataFrame(rows)


def ranking_diagnostics(saved: pd.DataFrame, prior: dict,
                        prior_games: pd.DataFrame, current: pd.DataFrame,
                        d1_ids: set[str], sport: str) -> tuple[pd.DataFrame, dict]:
    """Show rank plausibility signals, NOT independently verified 'inflation'."""
    required = {"Team ID", "Team", "Current power", "Preseason rating",
                "Games played", "On-court rating", "On-court weight"}
    if not required.issubset(saved):
        raise ValueError(f"Missing official rating fields: {sorted(required-set(saved))}")
    saved = saved.copy()
    saved["Team ID"] = saved["Team ID"].astype(str)
    if saved["Team ID"].duplicated().any():
        raise ValueError("Duplicate saved team rating IDs")
    for key in ("Current power", "Preseason rating", "Games played",
                "On-court rating", "On-court weight"):
        saved[key] = pd.to_numeric(saved[key], errors="coerce")
    eligible = saved[saved["Team ID"].isin(d1_ids)].dropna(
        subset=["Current power", "Preseason rating"]).sort_values("Current power", ascending=False)
    if len(eligible) < 200:
        raise ValueError(f"{sport}: incomplete saved D1 ranks")
    historical = sorted(((tid, power) for tid, power in prior.items() if tid in d1_ids),
                        key=lambda z: z[1], reverse=True)
    old_ranks = {tid: idx + 1 for idx, (tid, _) in enumerate(historical)}
    prior_games_by_team = _counts(prior_games)
    old_non_d1 = {}
    for g in prior_games.to_dict("records"):
        for team, opp in ((str(g["Home ID"]), str(g["Away ID"])),
                          (str(g["Away ID"]), str(g["Home ID"]))):
            if opp not in d1_ids:
                old_non_d1[team] = old_non_d1.get(team, 0) + 1
    season_gp = _counts(current)
    rows = []
    for index, rec in enumerate(eligible.head(25).to_dict("records"), start=1):
        tid = str(rec["Team ID"])
        oldrank = old_ranks.get(tid)
        gp = int(season_gp.get(tid, 0))
        rows.append({
            "division": sport, "current_d1_rank": index,
            "team_id": tid, "team": str(rec["Team"]),
            "saved_current_power": round(float(rec["Current power"]), 3),
            "saved_preseason_power": round(float(rec["Preseason rating"]), 3),
            "difference_vs_preseason": round(float(rec["Current power"]-rec["Preseason rating"]), 3),
            "preseason_d1_rank": oldrank,
            "rank_gain_vs_preseason": (oldrank-index) if oldrank is not None else None,
            "old_season_games": int(prior_games_by_team.get(tid, 0)),
            "old_season_opponents_not_in_current_d1_directory": int(old_non_d1.get(tid, 0)),
            "current_season_saved_finals": gp,
            "reported_games_played": (int(rec["Games played"]) if pd.notna(rec["Games played"]) else None),
            "on_court_weight": (float(rec["On-court weight"]) if pd.notna(rec["On-court weight"]) else None),
            "watch_signal_gain_10_plus_ranks": bool(oldrank is not None and oldrank-index >= 10),
            "watch_signal_top25_with_0_to_1_games": bool(gp <= 1),
        })
    table = pd.DataFrame(rows)
    named = table.loc[table["team"].str.contains("Akron", case=False, na=False)]
    akron = named.iloc[0].to_dict() if not named.empty else None
    if akron is None and sport.startswith("mens"):
        found = eligible[eligible["Team"].astype(str).str.contains("Akron", case=False, na=False)]
        if len(found) == 1:
            row = found.iloc[0]
            tid = str(row["Team ID"])
            rank = int(eligible.index.get_loc(found.index[0]) + 1)
            akron = {
                "team_id": tid, "team": str(row["Team"]), "current_d1_rank": rank,
                "preseason_d1_rank": old_ranks.get(tid),
                "current_power": float(row["Current power"]),
                "preseason_power": float(row["Preseason rating"]),
                "current_season_saved_finals": int(season_gp.get(tid, 0)),
            }
    return table, {
        "rated_current_d1": len(eligible),
        "top25_with_0_to_1_current_final": int(table["watch_signal_top25_with_0_to_1_games"].sum()),
        "top25_up_10_plus_preseason_ranks": int(table["watch_signal_gain_10_plus_ranks"].sum()),
        "top25_below_preseason_power": int((table["difference_vs_preseason"] < -0.025).sum()),
        "top25_above_preseason_power": int((table["difference_vs_preseason"] > 0.025).sum()),
        "akron_case": akron,
        "interpretation": "Rank gains and weak non-D1 schedule signals are review flags only, not a verified independent rank or proof a team is overvalued.",
    }


def research_main(root: Path, out: Path, asof: date, d1_lookup=None):
    if asof < date(2026, 11, 1):
        raise ValueError("V238 evaluation starts with 2026-27 season")
    if out.resolve() == root.resolve() or root.resolve() in out.resolve().parents:
        # If stored under repo, forbid writes under protected production areas.
        rel = out.resolve().relative_to(root.resolve())
        if not rel.parts or rel.parts[0] not in ("data", "research"):
            raise ValueError("Research output must be isolated from production directories")
        if rel.parts[0] == "data" and (len(rel.parts) < 2 or rel.parts[1] != "research_calibration_v238"):
            raise ValueError("Only data/research_calibration_v238/ may be written in repo")
    from reliability_v99 import fetch_d1_membership
    if d1_lookup is None:
        d1_lookup = fetch_d1_membership
    report = {
        "version": 238,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "asof_date": str(asof),
        "status": "RESEARCH_ONLY_RETROSPECTIVE_NOT_DEPLOYED",
        "divisions": {},
        "candidate_definitions": {
            "prior_only": "2025-26 game-margin fit, fixed throughout 2026-27",
            "legacy_replay": "production zero-centered ridge-8 on-court fit plus game-count phase-in, day-before replay",
            "anchored_ridge4": "margin cap 40, home advantage 3, ridge 4 around previous-season power",
            "anchored_ridge8": "margin cap 40, home advantage 3, ridge 8 around previous-season power",
            "anchored_ridge16": "margin cap 40, home advantage 3, ridge 16 around previous-season power",
        },
        "limitations": [
            "Retrospective date-only replay, NOT immutable first pregame forecasts.",
            "All matches on a target date are held out, but archived final-result availability times are unknown.",
            "Choice of candidate hypotheses follows earlier observations; current-season scores are exploratory, not independent holdout.",
            "Only games with both teams in the CURRENT verified ESPN D1 directory and previous-season prior fit are scored.",
            "Prior season's non-D1 opponent classification uses the current D1 list, not a historical membership snapshot.",
            "Prior scores include historical opponents not necessarily D1; no verified roster, coach, or transfer values are added.",
            "Strong-win changes compare before-day and after-day RETROSPECTIVE fits and may include other games on that date.",
            "Win by 25 points or more does not imply a mathematically required rating increase versus opponent expectations.",
            "Anchored alternative comparisons have not been promoted; use V97/V233/V235 prospective evidence for deployment.",
            "No production file, rating, first forecast, or ranking is modified.",
        ],
    }
    for sport in SPORTS:
        base = root / "data" / "ratings" / sport
        files = {name: base / filename for name, filename in (
            ("prior", "history_2025-26.csv.gz"),
            ("current", "season_2026-27.csv.gz"),
            ("saved", "latest.csv.gz"),
            ("status", "status.json"))}
        if not all(f.is_file() for f in files.values()):
            raise FileNotFoundError(f"{sport}: missing required immutable saved input")
        raw_prior = pd.read_csv(files["prior"], dtype={"Game ID": str, "Home ID": str, "Away ID": str})
        raw_current = pd.read_csv(files["current"], dtype={"Game ID": str, "Home ID": str, "Away ID": str})
        previous = normalize(raw_prior, "prior")
        current = normalize(raw_current, "current")
        current = current[(current["Day"] >= date(2026,11,1)) & (current["Day"] <= asof)].copy()
        ids = set(map(str, d1_lookup(sport)))
        prior = historical_prior(previous)
        saved = pd.read_csv(files["saved"], dtype={"Team ID": str})
        paired, evaluation, states = compare_chronologically(prior, current, ids, asof)
        wins = strong_win_diagnostics(prior, current, states, ids)
        top25, rank_report = ranking_diagnostics(saved, prior, previous, current, ids, sport)
        prefix = "mens" if sport.startswith("mens") else "womens"
        out.mkdir(parents=True, exist_ok=True)
        paired.to_csv(out / f"{prefix}_chronological_pairs.csv", index=False)
        wins.to_csv(out / f"{prefix}_strong_wins.csv", index=False)
        top25.to_csv(out / f"{prefix}_top25_watch.csv", index=False)
        report["divisions"][sport] = {
            "source_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest()
                              for name, path in files.items()},
            "saved_rating_status": json.loads(files["status"].read_text()),
            "verified_current_d1_teams": len(ids),
            "prior_final_games": len(previous),
            "current_final_games_at_or_before_asof": len(current),
            "current_d1_games_not_necessarily_scored": int(
                (current["Home ID"].isin(ids) & current["Away ID"].isin(ids)).sum()),
            "comparison": evaluation,
            "ranking_watch": rank_report,
            "strong_wins": {
                "all_25_plus_wins_for_verified_d1_teams": len(wins),
                "legacy_declines_after_25_plus_win": (int(wins["legacy_dropped_after_win"].sum())
                                                      if not wins.empty else 0),
                "anchored8_declines_after_25_plus_win": (
                    int((wins["anchored8_change_after_day"] < -0.025).sum()) if not wins.empty else 0),
            },
        }
    (out / "summary.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps(report, indent=2, default=str))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "research_calibration_v238")
    parser.add_argument("--asof", type=date.fromisoformat,
                        default=datetime.now(timezone.utc).date())
    opts = parser.parse_args()
    research_main(opts.root, opts.out, opts.asof)

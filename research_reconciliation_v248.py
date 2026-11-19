"""V248 research-only reconciliation of V247 game-count and blend-weight mismatches.

Compare *each saved snapshot* with cumulative archived final-game counts,
rather than assuming the final season archive reproduces every earlier data
state. Explicitly separate no-game schedule intervals from changes in saved
game counts. No production writes or retroactive causal claims.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from rating_engine import blending_weight
from research_rating_updates_v247 import (
    ROOT, SPORTS, read, validate_games, validate_snapshots, transitions,
)

TOL = 1e-6


def reconcile(snapshots: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    movement = transitions(snapshots, games).copy()
    if movement.empty:
        raise ValueError("No snapshot transitions")
    # A final archive reflects its current state, not necessarily the state at
    # each earlier snapshot. Count finals up to each endpoint independently.
    participants = pd.concat([
        games[["Date", "Home ID", "Game ID"]].rename(columns={"Home ID": "team_id"}),
        games[["Date", "Away ID", "Game ID"]].rename(columns={"Away ID": "team_id"}),
    ], ignore_index=True)
    if participants.duplicated(["team_id", "Game ID"]).any():
        raise ValueError("Same team repeated in final game archive")
    dates = sorted(snapshots["Snapshot date"].unique())
    totals = {}
    for day in dates:
        counts = participants[participants["Date"] <= day]["team_id"].value_counts()
        totals[day] = counts
    movement["archived_total_before"] = [
        int(totals[p].get(t, 0)) for p, t in
        zip(pd.to_datetime(movement["previous_date"]).dt.date, movement["team_id"])
    ]
    movement["archived_total_after"] = [
        int(totals[p].get(t, 0)) for p, t in
        zip(pd.to_datetime(movement["snapshot_date"]).dt.date, movement["team_id"])
    ]
    movement["archived_interval_delta"] = (
        movement["archived_total_after"]-movement["archived_total_before"])
    if not movement["archived_interval_delta"].eq(movement["opponent_schedule_games"]).all():
        raise ValueError("Cumulative and interval schedule counts disagree")
    movement["offset_before"] = movement["games_before"]-movement["archived_total_before"]
    movement["offset_after"] = movement["games_after"]-movement["archived_total_after"]
    movement["offset_change"] = movement["offset_after"]-movement["offset_before"]
    movement["weight_change"] = (
        movement["preseason_weight_after"]-movement["preseason_weight_before"])
    movement["expected_weight_before"] = movement["games_before"].map(
        lambda g: 1-blending_weight(int(g)))
    movement["expected_weight_after"] = movement["games_after"].map(
        lambda g: 1-blending_weight(int(g)))
    movement["weight_formula_mismatch"] = (
        (movement["expected_weight_before"]-movement["preseason_weight_before"]).abs() > TOL
    ) | (
        (movement["expected_weight_after"]-movement["preseason_weight_after"]).abs() > TOL
    )
    movement["unchanged_saved_games_weight_changed"] = (
        movement["games_delta"].eq(0) & movement["weight_change"].abs().gt(TOL))
    movement["snapshot_gap_days"] = (
        pd.to_datetime(movement["snapshot_date"])-
        pd.to_datetime(movement["previous_date"])).dt.days
    movement["archive_interval_disagreement"] = (
        movement["games_delta"] != movement["archived_interval_delta"])
    movement["category"] = np.select([
        movement["weight_formula_mismatch"],
        movement["unchanged_saved_games_weight_changed"],
        ~movement["archive_interval_disagreement"],
        movement["games_delta"].eq(0) & movement["archived_interval_delta"].gt(0),
        movement["games_delta"].gt(0) & movement["archived_interval_delta"].eq(0),
        movement["games_delta"].lt(0),
        movement["games_delta"].gt(movement["archived_interval_delta"]),
        movement["games_delta"].lt(movement["archived_interval_delta"]),
    ], [
        "blend_formula_inconsistent",
        "weight_changed_without_saved_game_change",
        "counts_agree",
        "archive_has_games_not_reflected_in_snapshot",
        "snapshot_added_games_absent_from_final_archive_interval",
        "saved_game_count_decreased",
        "snapshot_delta_exceeds_final_archive",
        "final_archive_delta_exceeds_snapshot",
    ], default="unclassified")
    return movement


def report(rows: pd.DataFrame) -> dict:
    categories = rows["category"].value_counts().to_dict()
    no_archive_games = rows[rows["archived_interval_delta"].eq(0)]
    no_saved_change = rows[rows["games_delta"].eq(0)]
    mismatch = rows[rows["archive_interval_disagreement"]]
    def describe(frame):
        return {"rows": len(frame),
                "mean_abs_rating_change": round(float(frame["rating_change"].abs().mean()), 5) if len(frame) else None,
                "mean_abs_blend_component": round(float(frame["blend_weight_component"].abs().mean()), 5) if len(frame) else None,
                "weight_changed_rows": int(frame["weight_change"].abs().gt(TOL).sum())}
    return {
        "total_team_transitions": len(rows),
        "category_counts": {str(k): int(v) for k, v in categories.items()},
        "schedule_mismatch": describe(mismatch),
        "no_games_in_final_archive_interval": describe(no_archive_games),
        "saved_game_count_unchanged": describe(no_saved_change),
        "both_counts_unchanged": describe(rows[rows["games_delta"].eq(0) &
                                             rows["archived_interval_delta"].eq(0)]),
        "saved_games_changed_but_no_archived_game": describe(
            rows[rows["games_delta"].ne(0) & rows["archived_interval_delta"].eq(0)]),
        "blend_formula_inconsistent_rows": int(rows["weight_formula_mismatch"].sum()),
        "unchanged_saved_games_weight_changed_rows": int(rows["unchanged_saved_games_weight_changed"].sum()),
        "gap_over_one_day_rows": int(rows["snapshot_gap_days"].gt(1).sum()),
        "offset_changed_rows": int(rows["offset_change"].ne(0).sum()),
        "offset_constant_mismatch_rows": int((rows["offset_change"].eq(0) &
                                              rows["offset_after"].ne(0)).sum()),
        "limitations": [
            "Final season archive is not a timestamped record of what was available at each prior snapshot.",
            "Archived game Date may be ESPN's eastern-time date, while snapshot date is the workflow's as-of date.",
            "Skipped snapshots and late score corrections can produce differences; these are hypotheses, not proven causes.",
            "Current final-game archive may contain games omitted or excluded by earlier fits; no original historical inputs are reconstructed.",
            "A zero-game interval can have a rating movement through league-wide on-court refits, but cannot change blend weight under the current formula.",
            "No model parameter, production rating, or forecast is changed.",
        ],
    }


def run(root: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    result = {"version": 248, "status": "RESEARCH_ONLY", "production_changed": False,
              "divisions": {}}
    for sport in SPORTS:
        base = root/"data/ratings"/sport
        snapshots = validate_snapshots(read(base/"history.csv.gz"))
        games = validate_games(read(base/"season_2026-27.csv.gz"))
        rows = reconcile(snapshots, games)
        result["divisions"][sport] = report(rows)
        rows.to_csv(out/f"{sport}_reconciliation.csv", index=False)
        rows[rows["archive_interval_disagreement"] | rows["weight_formula_mismatch"] |
             rows["unchanged_saved_games_weight_changed"]].to_csv(
            out/f"{sport}_exceptions.csv", index=False)
    (out/"summary.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=ROOT/"data/research_reconciliation_v248")
    args = parser.parse_args()
    run(args.root.resolve(), args.out.resolve())

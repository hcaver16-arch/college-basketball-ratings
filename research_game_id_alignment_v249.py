"""Courtside V249: game-ID evidence for Eastern-date / UTC-snapshot alignment.

Research-only: compare archived *final-state* game IDs with saved team-game
counts at alternate date cutoffs (-2 through +1 days). This can identify
alignment-consistent mismatches, NOT the real historical ingestion timestamp
of any game. Does not fetch ESPN, alter any production file, or tune ratings.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import defaultdict
from datetime import timedelta
import json
from pathlib import Path

import pandas as pd

from research_rating_updates_v247 import ROOT, SPORTS, read, validate_games, validate_snapshots
from research_reconciliation_v248 import reconcile

SHIFTS = (-2, -1, 0, 1)


def participation(games: pd.DataFrame) -> pd.DataFrame:
    """One identifiable participant row per validated final archive game."""
    home = games[["Game ID", "Date", "Home ID", "Away ID"]].rename(
        columns={"Game ID": "game_id", "Date": "et_day", "Home ID": "team_id",
                 "Away ID": "opponent_id"})
    away = games[["Game ID", "Date", "Away ID", "Home ID"]].rename(
        columns={"Game ID": "game_id", "Date": "et_day", "Away ID": "team_id",
                 "Home ID": "opponent_id"})
    p = pd.concat([home, away], ignore_index=True)
    if p.duplicated(["team_id", "game_id"]).any():
        raise ValueError("Duplicate participant/game ID records")
    p["team_id"] = p["team_id"].astype(str)
    p["game_id"] = p["game_id"].astype(str)
    return p.sort_values(["team_id", "et_day", "game_id"]).reset_index(drop=True)


def game_lookup(participants: pd.DataFrame):
    """Sorted per-team game dates and IDs for efficient date-window evidence."""
    lookup = {}
    for tid, group in participants.groupby("team_id"):
        lookup[str(tid)] = (
            group["et_day"].tolist(), group["game_id"].tolist())
    return lookup


def ids_between(lookup, team: str, start, end) -> list[str]:
    """Game IDs satisfying start < ET date <= end."""
    ds, ids = lookup.get(str(team), ([], []))
    return ids[bisect_right(ds, start):bisect_right(ds, end)]


def archived_counts(lookup, teams, days, shift: int):
    """Final-state cumulative games through snapshot UTC date + shift."""
    out = {}
    for day in days:
        cutoff = day+timedelta(days=shift)
        out[day] = {
            team: bisect_right(lookup.get(str(team), ([], []))[0], cutoff)
            for team in teams
        }
    return out


def audit(snaps: pd.DataFrame, games: pd.DataFrame):
    """Return snapshot cutoff scores, transition-level discrepancies and ID trace."""
    participants = participation(games)
    lookup = game_lookup(participants)
    teams = sorted(set(snaps["Team ID"].astype(str)))
    days = sorted(snaps["Snapshot date"].unique())
    caches = {shift: archived_counts(lookup, teams, days, shift) for shift in SHIFTS}

    # Do not choose a cutoff using only mismatched transitions: compare the
    # complete set of saved snapshots under the same fixed candidate shifts.
    date_team = snaps[["Snapshot date", "Team ID", "Games played"]].copy()
    date_team["team_id"] = date_team["Team ID"].astype(str)
    comparisons = []
    for shift in SHIFTS:
        expected = [caches[shift][day][tid] for day, tid in
                    zip(date_team["Snapshot date"], date_team["team_id"])]
        residual = date_team["Games played"].to_numpy(float)-expected
        comparisons.append({
            "cutoff_shift_days": shift,
            "snapshots_checked": len(date_team),
            "exact_count_match": int((abs(residual)<1e-9).sum()),
            "exact_match_rate": round(float((abs(residual)<1e-9).mean()), 6),
            "sum_abs_count_error": int(abs(residual).sum()),
            "mean_abs_count_error": round(float(abs(residual).mean()), 6),
            "max_abs_count_error": int(abs(residual).max()),
        })

    m = reconcile(snaps, games).copy()
    starts = pd.to_datetime(m["previous_date"]).dt.date.tolist()
    ends = pd.to_datetime(m["snapshot_date"]).dt.date.tolist()
    tids = m["team_id"].astype(str).tolist()
    for shift in SHIFTS:
        key = "minus"+str(abs(shift)) if shift < 0 else "plus"+str(shift)
        count = [
            caches[shift][end][tid]-caches[shift][start][tid]
            for start, end, tid in zip(starts, ends, tids)
        ]
        m["archive_interval_"+key] = count
        m["match_"+key] = m["games_delta"].eq(m["archive_interval_"+key])

    mismatch = m[m["archive_interval_disagreement"]].copy()
    minus1 = mismatch["match_minus1"]
    mismatch["alignment_class"] = "not_explained_by_one_day_cutoff"
    mismatch.loc[minus1, "alignment_class"] = "consistent_with_previous_ET_day_cutoff"
    mismatch.loc[~minus1 & mismatch["match_minus2"],
                 "alignment_class"] = "consistent_with_two_day_lag_only"
    mismatch.loc[~minus1 & ~mismatch["match_minus2"] & mismatch["match_plus1"],
                 "alignment_class"] = "consistent_with_next_day_cutoff_only"

    evidence = []
    trace_rows = []
    for idx, r in mismatch.iterrows():
        start, end = starts[idx], ends[idx]
        tid = tids[idx]
        prior_et = ids_between(lookup, tid, start-timedelta(days=1),
                               end-timedelta(days=1))
        nominal = ids_between(lookup, tid, start, end)
        neighborhood = ids_between(lookup, tid, start-timedelta(days=2),
                                   end+timedelta(days=1))
        evidence.append({
            "team_id": tid, "previous_snapshot": str(start),
            "current_snapshot": str(end),
            "saved_games_before": int(r["games_before"]),
            "saved_games_after": int(r["games_after"]),
            "saved_games_delta": int(r["games_delta"]),
            "nominal_ET_game_count": int(r["archived_interval_delta"]),
            "previous_ET_day_game_count": int(r["archive_interval_minus1"]),
            "classification": r["alignment_class"],
            "nominal_game_ids": "|".join(nominal),
            "previous_day_cutoff_game_ids": "|".join(prior_et),
            "nearby_candidate_game_ids": "|".join(neighborhood),
            "snapshot_gap_days": int(r["snapshot_gap_days"]),
            "offset_before": int(r["offset_before"]),
            "offset_after": int(r["offset_after"]),
        })
        # Explicit game IDs and day per flagged transition. These are
        # candidate associations, not proven snapshot-ingestion records.
        for gid in neighborhood:
            for item in participants[(participants["team_id"] == tid) &
                                     (participants["game_id"] == gid)].itertuples(index=False):
                trace_rows.append({
                    "game_id": gid, "team_id": tid,
                    "opponent_id": item.opponent_id,
                    "event_day_eastern": str(item.et_day),
                    "previous_snapshot": str(start),
                    "current_snapshot": str(end),
                    "in_nominal_interval": gid in nominal,
                    "in_previous_day_cutoff_interval": gid in prior_et,
                    "saved_games_delta": int(r["games_delta"]),
                    "classification": r["alignment_class"],
                })
    exceptions = pd.DataFrame(evidence, columns=[
        "team_id", "previous_snapshot", "current_snapshot",
        "saved_games_before", "saved_games_after", "saved_games_delta",
        "nominal_ET_game_count", "previous_ET_day_game_count",
        "classification", "nominal_game_ids", "previous_day_cutoff_game_ids",
        "nearby_candidate_game_ids", "snapshot_gap_days",
        "offset_before", "offset_after"])
    traces = pd.DataFrame(trace_rows, columns=[
        "game_id", "team_id", "opponent_id", "event_day_eastern",
        "previous_snapshot", "current_snapshot", "in_nominal_interval",
        "in_previous_day_cutoff_interval", "saved_games_delta", "classification"])
    return comparisons, m, exceptions, traces


def summarize(comparisons, transitions, exceptions, traces):
    def stats(frame):
        return {"transition_rows": int(len(frame)),
                "abs_rating_change_mean": round(float(frame["rating_change"].abs().mean()), 5)
                if len(frame) else None}
    baseline = transitions[transitions["archive_interval_disagreement"]]
    explained = baseline[baseline["match_minus1"]]
    return {
        "cutoff_comparisons": comparisons,
        "baseline_mismatches": stats(baseline),
        "mismatches_matching_previous_ET_day_cutoff": stats(explained),
        "still_unmatched_after_previous_ET_day_cutoff": int(
            len(baseline)-len(explained)),
        "mismatch_categories": {str(k): int(v) for k, v in
                                exceptions["classification"].value_counts().items()},
        "candidate_game_id_rows": int(len(traces)),
        "candidate_unique_game_ids": int(traces["game_id"].nunique()),
        "limitations": [
            "A game ID in the final-state archive is not proof of when its score was first ingested.",
            "Snapshot dates are UTC as-of dates; archived game dates come from the ESPN event time converted to America/New_York in daily_ratings.py.",
            "The scheduled refresh is at 12:30 UTC; actual execution may be delayed and reruns are possible.",
            "Cutoff shifts are descriptive competing hypotheses, not adjustments to production ratings.",
            "Earlier Git revisions of the game archive and timestamped per-game ingestion logs are not reconstructed here.",
            "Late updates, timezone dates, and other archive differences can still explain residual mismatches.",
            "Match rates include teams with no games; also evaluate mismatch resolution and residuals, not only percentages.",
        ],
    }


def run(root: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    result = {"version": 249, "status": "RESEARCH_ONLY_NOT_DEPLOYED",
              "production_changed": False, "divisions": {}}
    for division in SPORTS:
        base = root/"data/ratings"/division
        snaps = validate_snapshots(read(base/"history.csv.gz"))
        games = validate_games(read(base/"season_2026-27.csv.gz"))
        comparisons, movements, exceptions, traces = audit(snaps, games)
        result["divisions"][division] = summarize(
            comparisons, movements, exceptions, traces)
        exceptions.to_csv(output/f"{division}_exception_game_ids.csv", index=False)
        traces.to_csv(output/f"{division}_game_id_candidates.csv", index=False)
        movements[["team_id", "previous_date", "snapshot_date",
                   "games_delta", "archived_interval_delta",
                   "archive_interval_minus2", "archive_interval_minus1",
                   "archive_interval_plus0", "archive_interval_plus1",
                   "archive_interval_disagreement", "match_minus1",
                   "snapshot_gap_days"]].to_csv(
                       output/f"{division}_cutoff_comparisons.csv", index=False)
    (output/"summary.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--output", type=Path, default=ROOT/"data/research_game_id_alignment_v249")
    a = p.parse_args()
    run(a.root.resolve(), a.output.resolve())

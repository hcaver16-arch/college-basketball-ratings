"""Regression tests for V249 retrospective game-ID alignment evidence."""
import unittest
import pandas as pd

from rating_engine import blending_weight
from research_rating_updates_v247 import validate_games, validate_snapshots
from research_game_id_alignment_v249 import (
    audit, participation, game_lookup, ids_between, summarize,
)


def fixture_snapshots(counts=(0, 0, 1)):
    records = []
    for day, count in zip(("2026-11-01", "2026-11-02", "2026-11-03"), counts):
        w = 1-blending_weight(count)
        for team in ("101", "202"):
            records.append({
                "Snapshot date": day, "Team ID": team,
                "Games played": count,
                "Preseason weight": w,
                "Preseason rating": 10.,
                "On-court rating": 0.,
                "Current power": 10*w,
            })
    return validate_snapshots(pd.DataFrame(records))


def fixture_games():
    return validate_games(pd.DataFrame([{
        "Game ID": "401234567", "Date": "2026-11-02", "Status": "Final",
        "Home ID": "101", "Away ID": "202", "Home score": 75,
        "Away score": 55, "Venue": "Home",
    }]))


class V249Tests(unittest.TestCase):
    def test_day_minus_one_resolves_pair_of_mismatches(self):
        comp, movement, exceptions, trace = audit(
            fixture_snapshots(), fixture_games())
        self.assertEqual(len(exceptions), 4)
        self.assertEqual(set(exceptions["classification"]),
                         {"consistent_with_previous_ET_day_cutoff"})
        self.assertEqual(int(movement["match_minus1"].sum()), 4)
        self.assertEqual(int(movement["archive_interval_disagreement"].sum()), 4)
        self.assertEqual(comp[1]["cutoff_shift_days"], -1)
        self.assertEqual(comp[1]["exact_count_match"], 6)
        self.assertEqual(comp[2]["exact_count_match"], 4)
        self.assertEqual(set(trace["game_id"]), {"401234567"})
        self.assertTrue(all(exceptions["nearby_candidate_game_ids"].str.contains("401234567")))

    def test_extra_unexplained_game_count_is_not_labeled_ingested(self):
        comp, movement, exceptions, trace = audit(
            fixture_snapshots((0, 0, 2)), fixture_games())
        summary = summarize(comp, movement, exceptions, trace)
        self.assertGreater(summary["still_unmatched_after_previous_ET_day_cutoff"], 0)
        self.assertFalse(
            exceptions["classification"].eq(
                "consistent_with_previous_ET_day_cutoff").all())

    def test_game_ids_filter_by_eastern_date(self):
        p = participation(fixture_games())
        lookup = game_lookup(p)
        from datetime import date
        self.assertEqual(
            ids_between(lookup, "101", date(2026, 11, 1), date(2026, 11, 2)),
            ["401234567"])
        self.assertEqual(
            ids_between(lookup, "101", date(2026, 11, 2), date(2026, 11, 3)),
            [])
        self.assertEqual(ids_between(lookup, "missing", date(2026, 11, 1),
                                     date(2026, 11, 3)), [])


if __name__ == "__main__":
    unittest.main()

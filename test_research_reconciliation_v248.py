import unittest
import pandas as pd
from rating_engine import blending_weight
from research_rating_updates_v247 import validate_snapshots, validate_games
from research_reconciliation_v248 import reconcile, report


def snapshots(counts=(0, 1, 1), weights=None):
    rows = []
    for i, date in enumerate(("2026-11-01", "2026-11-02", "2026-11-03")):
        for team in ("1", "2"):
            games = counts[i]
            w = 1-blending_weight(games) if weights is None else weights[i]
            rows.append({"Snapshot date": date, "Team ID": team,
                "Current power": 10*w, "Preseason rating": 10.,
                "On-court rating": 0., "Games played": games,
                "Preseason weight": w})
    return validate_snapshots(pd.DataFrame(rows))


def games():
    return validate_games(pd.DataFrame([{"Game ID": "g", "Date": "2026-11-02",
        "Status": "Final", "Home ID": "1", "Away ID": "2",
        "Home score": 75, "Away score": 60, "Venue": "Home"}]))


class V248Tests(unittest.TestCase):
    def test_matching_counts_and_no_game_weights(self):
        rows = reconcile(snapshots(), games())
        self.assertEqual(len(rows), 4)
        self.assertEqual(report(rows)["schedule_mismatch"]["rows"], 0)
        self.assertEqual(report(rows)["unchanged_saved_games_weight_changed_rows"], 0)
        self.assertEqual(report(rows)["both_counts_unchanged"]["rows"], 2)

    def test_archive_missing_from_snapshot(self):
        rows = reconcile(snapshots((0, 0, 0)), games())
        self.assertEqual(report(rows)["category_counts"][
            "archive_has_games_not_reflected_in_snapshot"], 2)
        self.assertEqual(report(rows)["schedule_mismatch"]["rows"], 2)

    def test_snapshot_count_change_without_archive_game(self):
        rows = reconcile(snapshots((0, 0, 1)), games())
        self.assertEqual(report(rows)["category_counts"][
            "snapshot_added_games_absent_from_final_archive_interval"], 2)

    def test_weight_formula_violation_is_flagged(self):
        bad = snapshots((0, 0, 0), weights=(1., .95, .95))
        rows = reconcile(bad, games())
        self.assertGreater(report(rows)["blend_formula_inconsistent_rows"], 0)
        self.assertGreater(report(rows)["unchanged_saved_games_weight_changed_rows"], 0)

    def test_duplicate_final_rejected(self):
        raw = pd.DataFrame([{"Game ID": "g", "Date": "2026-11-02",
            "Status": "Final", "Home ID": "1", "Away ID": "2",
            "Home score": 75, "Away score": 60, "Venue": "Home"}])
        with self.assertRaises(ValueError):
            validate_games(pd.concat([raw, raw], ignore_index=True))


if __name__ == "__main__":
    unittest.main()

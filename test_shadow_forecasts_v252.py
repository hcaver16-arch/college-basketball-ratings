"""V252 regression tests: immutable genuine pre-tip pairing and evaluations."""
import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd

from shadow_forecasts_v252 import (
    FIELDS, METHODS, MAX_CAPTURE_LAG, append_first, candidate_rows,
    evaluate, final_training_games, metrics, timestamp,
)

UTC = timezone.utc
NOW = datetime(2026, 11, 20, 12, 40, tzinfo=UTC)
SNAPSHOT = datetime(2026, 11, 20, 12, 30, tzinfo=UTC)
LOCK = datetime(2026, 11, 20, 12, 32, tzinfo=UTC)
TIP = datetime(2026, 11, 20, 23, 0, tzinfo=UTC)


def rated():
    return pd.DataFrame([
        {"Team ID": "1", "Team": "Alpha",
         "Current power": 10., "Preseason rating": 12.,
         "Games played": 1, "As of UTC": SNAPSHOT.isoformat()},
        {"Team ID": "2", "Team": "Beta",
         "Current power": -5., "Preseason rating": -2.,
         "Games played": 1, "As of UTC": SNAPSHOT.isoformat()},
    ])


def official(**updates):
    d = {
        "Division": "mens-college-basketball", "Game ID": "upcoming",
        "Game start UTC": TIP.isoformat(),
        "First forecast UTC": LOCK.isoformat(), "Home ID": "1",
        "Away ID": "2", "Home": "Alpha", "Away": "Beta",
        "Venue": "Home", "Baseline home margin": 18.,
        "Rating snapshot date": SNAPSHOT.isoformat(),
    }
    d.update(updates)
    return pd.DataFrame([d])


def scheduled_final_input():
    # Current archive contains completed past games and scheduled future
    # games, but the latter must never influence the anchored model.
    return pd.DataFrame([
        {"Game ID": "previous", "Home ID": "1", "Away ID": "2",
         "Status": "Final", "Venue": "Home", "Home score": 80,
         "Away score": 63, "Date": "2026-11-19"},
        {"Game ID": "upcoming", "Home ID": "1", "Away ID": "2",
         "Status": "Scheduled", "Venue": "Home", "Home score": None,
         "Away score": None, "Date": "2026-11-20"},
    ])


def classifications():
    return pd.DataFrame([{"Game ID": "upcoming", "Matchup class": "D1 vs D1"}])


def capture(first=None, past=None, existing=None, when=NOW):
    return candidate_rows(
        official() if first is None else first,
        pd.DataFrame(columns=FIELDS) if existing is None else existing,
        rated(), scheduled_final_input() if past is None else past,
        classifications(), when, "mens-college-basketball",
        "rating_source_sha", "final_source_sha")


class V252Tests(unittest.TestCase):
    def test_new_first_pair_is_locked_before_tip_and_matched_to_snapshot(self):
        new, counts = capture()
        self.assertEqual(len(new), 1)
        self.assertEqual(counts["captured"], 1)
        x = new.iloc[0]
        self.assertEqual(x["Matchup class"], "D1 vs D1")
        self.assertEqual(x["Baseline home margin"], 18.)
        self.assertAlmostEqual(x["Prior-only home margin"], 17.)
        self.assertLess(timestamp(x["Shadow first forecast UTC"]),
                        timestamp(x["Game start UTC"]))
        self.assertEqual(x["Source rating SHA256"], "rating_source_sha")
        self.assertNotAlmostEqual(x["Anchored ridge8 home margin"],
                                  x["Anchored ridge16 home margin"])
        self.assertEqual(x["Home games at capture"], 1)

    def test_capture_never_changes_first_immutable_values(self):
        new, _ = capture()
        current = append_first(pd.DataFrame(columns=FIELDS), new)
        different = new.copy()
        different.loc[0, "Anchored ridge8 home margin"] = 999.
        with self.assertRaises(ValueError):
            append_first(current, different)
        next_run, counts = capture(existing=current)
        self.assertTrue(next_run.empty)
        self.assertEqual(counts["already_shadow_locked"], 1)
        self.assertEqual(current.loc[0, "Anchored ridge8 home margin"],
                         new.loc[0, "Anchored ridge8 home margin"])

    def test_old_official_lock_cannot_be_backfilled(self):
        lock = NOW-MAX_CAPTURE_LAG-timedelta(minutes=1)
        stale_official = official(**{
            "First forecast UTC": lock.isoformat()})
        new, reason = capture(first=stale_official)
        self.assertEqual(len(new), 0)
        self.assertEqual(reason["official_lock_too_old"], 1)

    def test_after_kickoff_cannot_capture(self):
        new, reason = capture(when=TIP+timedelta(minutes=1))
        self.assertTrue(new.empty)
        self.assertGreater(reason["not_pre_tip"], 0)

    def test_fresh_official_lock_requires_matching_current_ratings_snapshot(self):
        new, reason = capture(first=official(**{
            "Rating snapshot date": "2026-11-19T12:30:00+00:00"}))
        self.assertTrue(new.empty)
        self.assertEqual(reason["rating_snapshot_mismatch"], 1)
        new, reason = capture(first=official(**{
            "Baseline home margin": 10.}))
        self.assertTrue(new.empty)
        self.assertEqual(reason["rating_snapshot_mismatch"], 1)

    def test_scheduled_games_do_not_enter_training(self):
        raw = scheduled_final_input()
        x = final_training_games(raw)
        self.assertEqual(x["Game ID"].tolist(), ["previous"])
        altered = raw.copy()
        altered.loc[1, "Home score"] = 200
        altered.loc[1, "Away score"] = 1
        n1, _ = capture(past=raw)
        n2, _ = capture(past=altered)
        self.assertAlmostEqual(n1.iloc[0]["Anchored ridge8 home margin"],
                               n2.iloc[0]["Anchored ridge8 home margin"])

    def test_immutable_pre_tip_evaluation_and_same_games(self):
        shadow, _ = capture()
        later = scheduled_final_input()
        later.loc[1, "Status"] = "Final"
        later.loc[1, "Home score"] = 87.
        later.loc[1, "Away score"] = 64.
        evaluated = evaluate(shadow, later)
        self.assertEqual(len(evaluated), 1)
        self.assertAlmostEqual(evaluated.iloc[0]["Actual home margin"], 23.)
        summary = metrics(evaluated)
        self.assertEqual(summary["d1_vs_d1_primary"]["paired_games"], 1)
        self.assertEqual(set(summary["d1_vs_d1_primary"]["models"]), set(METHODS))
        self.assertTrue(summary["not_enough_games_to_select_model"])

    def test_evaluation_rejects_backdated_pretip_claim(self):
        shadow, _ = capture()
        shadow.loc[0, "Shadow first forecast UTC"] = (
            TIP+timedelta(minutes=1)).isoformat()
        with self.assertRaises(ValueError):
            evaluate(shadow, scheduled_final_input())

    def test_only_same_team_ids_score_results(self):
        shadow, _ = capture()
        later = scheduled_final_input()
        later.loc[1, "Status"] = "Final"
        later.loc[1, "Home score"] = 80.
        later.loc[1, "Away score"] = 70.
        later.loc[1, "Home ID"] = "999"
        self.assertTrue(evaluate(shadow, later).empty)

    def test_source_timestamp_older_than_grace_skips_new_predictions(self):
        new, reasons = capture(when=NOW+timedelta(hours=4))
        self.assertTrue(new.empty)
        self.assertTrue(reasons["stale_rating_snapshot"])


if __name__ == "__main__":
    unittest.main()

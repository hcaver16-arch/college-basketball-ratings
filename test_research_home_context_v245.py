import unittest
import pandas as pd
from research_home_context_v245 import analyze, prepare


def sample():
    return pd.DataFrame([
        {"game_id": str(i), "day": "2026-11-10",
         "cap_fit_latest_training_day": "2026-11-09",
         "neutral": "True" if i % 3 == 0 else "False",
         "prior_home": 20 if i % 2 else 5,
         "prior_away": 5 if i % 2 else 20,
         "prior_opponent_quality_quartile": "Q2",
         "prior_gap_bucket": "5_to_15", "early_games_bucket": "both_0_to_2",
         "actual_margin": 12 if i % 2 else -12,
         "anchored_cap40": 8 if i % 2 else -8,
         "anchored_ridge8": 8 if i % 2 else -8,
         "home_gp_before": 1, "away_gp_before": 1}
        for i in range(1, 61)])


class V245Tests(unittest.TestCase):
    def test_stratified_no_model_mutation(self):
        raw = sample()
        original = raw.copy(deep=True)
        report = analyze(raw, "mens")
        self.assertEqual(report["games"], 60)
        self.assertEqual(sum(x["games"] for x in report["all_by_venue"]), 60)
        self.assertTrue(report["matched_preseason_context"])
        pd.testing.assert_frame_equal(raw, original)

    def test_reject_future_training(self):
        data = sample()
        data.loc[0, "cap_fit_latest_training_day"] = "2026-11-10"
        with self.assertRaises(ValueError):
            prepare(data)

    def test_reject_missing_venue_and_changed_baseline(self):
        data = sample()
        data.loc[0, "neutral"] = "unknown"
        with self.assertRaises(ValueError):
            prepare(data)
        data = sample()
        data.loc[0, "anchored_cap40"] = 100
        with self.assertRaises(ValueError):
            prepare(data)


if __name__ == "__main__":
    unittest.main()

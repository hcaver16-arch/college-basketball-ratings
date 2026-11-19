import unittest
import pandas as pd
from research_calibration_v244 import evaluate_matched, verify_v239, verify_v240, compare


class HistoricalV244Tests(unittest.TestCase):
    def fixtures(self):
        a = pd.DataFrame([{
            "game_id": str(i), "day": "2025-12-04", "origin": "2025-12-01",
            "last_training_day": "2025-11-30", "actual_margin": 12.0,
            "s100_h3": 7.0, "s125_h3": 10.0, "s150_h3": 13.0,
            "trained_selected_prediction": 10.0} for i in range(1, 41)])
        b = pd.DataFrame([{
            "game_id": str(i), "day": "2026-11-04",
            "cap_fit_latest_training_day": "2026-11-03",
            "actual_margin": 50.0, "anchored_ridge8": 20.0,
            "anchored_cap20": 10.0, "anchored_cap40": 20.0,
            "anchored_cap60": 25.0} for i in range(1, 41)])
        return a, b

    def test_matched_and_metrics(self):
        a, b = self.fixtures()
        report = compare("mens", a, b)
        self.assertEqual(report["scale_study"]["results"][0]["games"], 40)
        self.assertEqual(report["scale_study"]["results"][1]["delta_mae_vs_reference"], -3)
        self.assertEqual(report["cap_study"]["results"][2]["delta_mae_vs_reference"], -5)
        self.assertFalse(report["production_change"])

    def test_refuse_temporal_leakage(self):
        a, b = self.fixtures()
        a.loc[0, "last_training_day"] = "2025-12-04"
        with self.assertRaises(ValueError):
            verify_v240(a)
        _, b = self.fixtures()
        b.loc[0, "cap_fit_latest_training_day"] = "2026-11-04"
        with self.assertRaises(ValueError):
            verify_v239(b)

    def test_refuse_unequal_or_changed_baseline(self):
        a, b = self.fixtures()
        a.loc[0, "s125_h3"] = float("nan")
        with self.assertRaises(ValueError):
            evaluate_matched(a, ("s100_h3", "s125_h3"), "actual_margin", reference="s100_h3")
        b.loc[0, "anchored_cap40"] = 21
        with self.assertRaises(ValueError):
            verify_v239(b)


if __name__ == "__main__":
    unittest.main()

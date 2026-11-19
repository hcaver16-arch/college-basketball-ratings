import unittest
import pandas as pd
from prediction_bias_v243 import prepare, segment, constant_shift_sensitivity


class BiasV243Tests(unittest.TestCase):
    def test_pre_tip_and_non_d1_excluded(self):
        def row(i, saved, classification, pred, actual):
            return {"Game ID": str(i), "Game start UTC": "2026-11-10T20:00:00Z",
                    "First forecast UTC": saved, "Matchup class": classification,
                    "Baseline home margin": pred, "Actual home margin": actual}
        raw = pd.DataFrame([
            row(1, "2026-11-10T19:00:00Z", "D1 vs D1", 8, 13),
            row(2, "2026-11-10T19:00:00Z", "D1 vs D1", -8, -11),
            row(3, "2026-11-10T21:00:00Z", "D1 vs D1", 8, 30),
            row(4, "2026-11-10T19:00:00Z", "D1 vs non-D1", 8, 30)])
        games, rejected = prepare(raw)
        self.assertEqual(rejected, 1)
        self.assertEqual(len(games), 2)
        groups = segment(games, ["Predicted favorite", "Favorite magnitude"])
        self.assertEqual(groups["Games"].sum(), 2)
        self.assertEqual(set(groups["Predicted favorite"]), {"Home", "Away"})
        offsets = constant_shift_sensitivity(games)
        self.assertEqual(offsets.iloc[0]["Signed bias"], 1.0)
        self.assertEqual(offsets.iloc[0]["MAE"], 4.0)
        self.assertEqual(offsets.iloc[0]["Winner accuracy %"], 100.0)

    def test_empty(self):
        self.assertTrue(segment(pd.DataFrame(), ["Predicted favorite"]).empty)
        self.assertTrue(constant_shift_sensitivity(pd.DataFrame()).empty)


if __name__ == "__main__":
    unittest.main()

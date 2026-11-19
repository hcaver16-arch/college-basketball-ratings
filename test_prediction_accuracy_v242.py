"""V242 regression tests: use the existing verified pre-tip archive gate."""
import unittest
import pandas as pd
from prediction_accuracy_v242 import accuracy_rows, summarize


class V242Tests(unittest.TestCase):
    def test_excludes_post_tip_and_non_d1(self):
        data = pd.DataFrame([
            {"Game ID": "1", "Game start UTC": "2026-11-10T20:00:00Z",
             "First forecast UTC": "2026-11-10T19:00:00Z",
             "Baseline home margin": 8, "Actual home margin": 3, "Matchup class": "D1 vs D1"},
            {"Game ID": "2", "Game start UTC": "2026-11-10T20:00:00Z",
             "First forecast UTC": "2026-11-10T20:30:00Z",
             "Baseline home margin": 8, "Actual home margin": 3, "Matchup class": "D1 vs D1"},
            {"Game ID": "3", "Game start UTC": "2026-11-10T20:00:00Z",
             "First forecast UTC": "2026-11-10T19:00:00Z",
             "Baseline home margin": 8, "Actual home margin": 3, "Matchup class": "D1 vs non-D1"},
        ])
        games, rejected = accuracy_rows(data)
        self.assertEqual(rejected, 1)
        self.assertEqual(len(games), 1)
        self.assertEqual(games.iloc[0]["Signed error"], -5)
        result = summarize(games, "Favorite size")
        self.assertEqual(result.iloc[0]["MAE"], 5)
        self.assertEqual(result.iloc[0]["Winner accuracy"], 100.0)

    def test_no_unsupported_d1_classification(self):
        data = pd.DataFrame([{
            "Game ID": "1", "Game start UTC": "2026-11-10T20:00:00Z",
            "First forecast UTC": "2026-11-10T19:00:00Z",
            "Baseline home margin": 8, "Actual home margin": 3,
        }])
        games, _ = accuracy_rows(data)
        self.assertTrue(games.empty)


if __name__ == "__main__":
    unittest.main()

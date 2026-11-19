import unittest
import numpy as np
import pandas as pd
from research_interaction_v246 import historical, predict, prospective_audit


def fixture():
    rows = []
    for month in (12, 1, 2, 3, 4):
        year = 2025 if month == 12 else 2026
        for i in range(130):
            gap = float(i % 20 - 5)
            home = int(i % 4 != 0)
            base = gap + 3*home
            rows.append({"game_id": f"{month}-{i}", "day": f"{year}-{month:02d}-10",
                         "origin": f"{year}-{month:02d}-01",
                         "last_training_day": f"{year}-{month:02d}-01" if False else
                             ("2025-11-30" if month == 12 else f"{year}-{month:02d}-01"),
                         "actual_margin": base + 2*home*(gap > 0),
                         "s100_h3": base, "prior_gap": gap,
                         "home_designated": home, "home_prior_power": gap+2,
                         "away_prior_power": 2.0})
    data = pd.DataFrame(rows)
    data["last_training_day"] = data["origin"].map(
        lambda x: str((pd.Timestamp(x)-pd.Timedelta(days=1)).date()))
    return data


class V246Tests(unittest.TestCase):
    def test_time_ordered_folds(self):
        report = historical(fixture())
        self.assertTrue(report["first_fold_not_scored"])
        self.assertEqual(report["evaluated_games"], 520)
        self.assertEqual(len(report["folds"]), 5)
        self.assertLess(report["overall"]["home_favorite"]["mae"],
                        report["overall"]["baseline"]["mae"])

    def test_reject_leakage(self):
        data = fixture()
        data.loc[0, "last_training_day"] = data.loc[0, "origin"]
        with self.assertRaises(ValueError):
            historical(data)

    def test_fixed_baseline(self):
        data = fixture()
        np.testing.assert_array_equal(predict(data.iloc[:130], data.iloc[130:140], "baseline"),
                                      data.iloc[130:140]["s100_h3"].to_numpy())

    def test_no_fake_prospective_scores(self):
        self.assertEqual(prospective_audit(pd.DataFrame())["games"], 0)


if __name__ == "__main__":
    unittest.main()

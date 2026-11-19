import unittest
import pandas as pd
from research_rating_updates_v247 import validate_snapshots, validate_games, transitions, game_surprises, summarize


def snapshots():
    rows=[]
    for date, a, b in (("2026-11-01", 10., -10.),
                       ("2026-11-02", 11., -11.),
                       ("2026-11-03", 11.5, -11.5)):
        for team, power in (("1", a), ("2", b)):
            rows.append({"Snapshot date": date, "Team ID": team,
                "Current power": power, "Preseason rating": power,
                "On-court rating": float("nan"), "Games played": 0,
                "Preseason weight": 1.})
    return pd.DataFrame(rows)


def games():
    return pd.DataFrame([{"Game ID": "g1", "Date": "2026-11-02",
        "Status": "Final", "Home ID": "1", "Away ID": "2",
        "Home score": 100, "Away score": 45, "Venue": "Home"}])


class V247Tests(unittest.TestCase):
    def test_no_game_day_movements_are_retained(self):
        snap = validate_snapshots(snapshots())
        match = validate_games(games())
        changes = transitions(snap, match)
        self.assertEqual(len(changes), 4)
        self.assertEqual(int(changes["did_not_play"].sum()), 2)
        self.assertAlmostEqual(changes.iloc[0]["rating_change"], 1)
        self.assertEqual(summarize(changes, game_surprises(snap, match))["blowout_over_40_games"], 1)

    def test_strict_prior_snapshot(self):
        gameset = game_surprises(validate_snapshots(snapshots()), validate_games(games()))
        self.assertEqual(len(gameset), 1)
        self.assertEqual(gameset.iloc[0]["last_snapshot"], "2026-11-01")
        self.assertAlmostEqual(gameset.iloc[0]["expected_margin_from_saved_ratings"], 23)
        self.assertAlmostEqual(gameset.iloc[0]["capped_margin"], 40)

    def test_reject_invalid_blend_identity(self):
        raw = snapshots()
        raw.loc[0, "Current power"] = 999
        with self.assertRaises(ValueError):
            validate_snapshots(raw)

    def test_reject_duplicate_team_day(self):
        raw = snapshots()
        with self.assertRaises(ValueError):
            validate_snapshots(pd.concat([raw, raw.iloc[[0]]], ignore_index=True))


if __name__ == "__main__":
    unittest.main()

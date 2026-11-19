"""V250 research-only regression and chronological isolation checks."""
import unittest
from datetime import date

import pandas as pd

from rating_engine import blending_weight
from research_rating_response_v250 import audit, components, summarize


def fixture_snapshots(*, winner_court=15., loser_court=-5., after_counts=(1, 1, 0)):
    before_strength = {"101": 10., "202": 0., "303": 4.}
    after_court = {"101": winner_court, "202": loser_court, "303": 0.}
    rows = []
    for day, counts in (
        ("2026-11-02", (0, 0, 0)),
        ("2026-11-03", after_counts),
    ):
        for index, team in enumerate(("101", "202", "303")):
            count = counts[index]
            weight = 1-blending_weight(count)
            prior = before_strength[team]
            court = after_court[team] if count else float("nan")
            power = weight*prior + (1-weight)*(0 if pd.isna(court) else court)
            rows.append({"Snapshot date": day, "Team ID": team,
                         "Team": "team"+team, "Games played": count,
                         "Preseason rating": prior,
                         "On-court rating": court,
                         "Preseason weight": weight, "Current power": power})
    return pd.DataFrame(rows)


def fixture_game(date_str="2026-11-02", margin=20, game_id="G1",
                 home="101", away="202"):
    return {"Game ID": game_id, "Date": date_str,
            "Status": "Final", "Home ID": home, "Away ID": away,
            "Home score": 70+margin, "Away score": 70,
            "Venue": "Home"}


def fixture_games(*extra):
    return pd.DataFrame([fixture_game(), *extra])


class V250Tests(unittest.TestCase):
    def test_production_response_and_opponent_context(self):
        evidence, coverage = audit(fixture_snapshots(), fixture_games())
        self.assertEqual(coverage["eligible_games"], 1)
        self.assertEqual(len(evidence), 2)
        winner = evidence[evidence["team_id"] == "101"].iloc[0]
        loser = evidence[evidence["team_id"] == "202"].iloc[0]
        self.assertAlmostEqual(winner["expected_margin_proxy"], 13.)
        self.assertAlmostEqual(winner["surprise_raw"], 7.)
        self.assertAlmostEqual(winner["rating_change"], .35, places=5)
        self.assertAlmostEqual(loser["rating_change"], -.35, places=5)
        self.assertEqual(winner["result"], "win")
        self.assertEqual(loser["result"], "loss")
        self.assertEqual(winner["phase"], "0-2 previous games")
        self.assertAlmostEqual(winner["no_game_median_change"], 0)
        self.assertEqual(coverage["snapshot_archive_count_inconsistent"], 0)
        self.assertEqual(len(summarize(evidence, coverage)["by_result"]), 2)

    def test_win_down_and_loss_up_are_descriptive_not_suppressed(self):
        evidence, _ = audit(fixture_snapshots(
            winner_court=-20., loser_court=20.), fixture_games())
        self.assertEqual(set(evidence["unusual_direction"]), {
            "win_and_rating_fell", "loss_and_rating_rose"})
        self.assertTrue(evidence.loc[
            evidence["result"] == "win", "rating_change"].iloc[0] < 0)

    def test_no_future_game_leakage(self):
        evidence, coverage = audit(
            fixture_snapshots(), fixture_games(
                fixture_game(date_str="2026-11-03", game_id="G2",
                             home="101", away="303")))
        self.assertEqual(len(evidence), 2)
        self.assertEqual(coverage["missing_adjacent_daily_snapshot"], 1)
        self.assertEqual(set(evidence["game_id"]), {"G1"})

    def test_ambiguous_same_day_multiple_games_excluded(self):
        evidence, coverage = audit(
            fixture_snapshots(), fixture_games(
                fixture_game(game_id="G2", home="101", away="303")))
        self.assertEqual(len(evidence), 0)
        self.assertEqual(coverage["non_isolated_team_game"], 2)

    def test_games_played_archive_mismatch_excluded(self):
        evidence, coverage = audit(
            fixture_snapshots(after_counts=(0, 1, 0)), fixture_games())
        self.assertEqual(len(evidence), 0)
        self.assertEqual(coverage["snapshot_archive_count_inconsistent"], 1)

    def test_cap40_changes_surprise_not_actual_final(self):
        evidence, _ = audit(fixture_snapshots(), fixture_games().assign(
            **{"Home score": [130]}))
        home = evidence[evidence["side"] == "home"].iloc[0]
        self.assertTrue(home["blowout_over_40"])
        self.assertAlmostEqual(home["actual_margin"], 60.)
        self.assertAlmostEqual(home["capped_margin"], 40.)
        self.assertAlmostEqual(home["surprise_cap40"], 27.)

    def test_blend_identity_guard(self):
        left = pd.Series({"Preseason weight": 1., "Preseason rating": 10.,
                          "On-court rating": float("nan"), "Current power": 10.})
        right = pd.Series({"Preseason weight": .93, "Preseason rating": 10.,
                           "On-court rating": 15., "Current power": 10.35})
        c = components(left, right)
        self.assertAlmostEqual(c["rating_change"],
                               c["prior_component"]+
                               c["on_court_component"]+c["blend_component"])


if __name__ == "__main__":
    unittest.main()

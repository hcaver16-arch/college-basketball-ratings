"""V261: explain adjusted-efficiency sample shortfalls without inventing metrics."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

import pandas as pd

from adjusted_efficiency import MIN_QUALIFYING_GAMES, fit_adjusted_efficiency
from adjusted_display import merge_team_stats
from efficiency_ui import _adjusted_sample_shortfall, _value


class AdjustedSampleNoticeTests(TestCase):
    def setUp(self):
        self.snapshot = "2026-11-25T20:37:53Z"
        self.raw = {
            "validated": True,
            "efficiency_games": 4,
            "off_eff": 115.2,
            "def_eff": 91.0,
            "net_eff": 24.2,
            "tempo": 68.8,
        }

    def test_constant_is_actual_model_default(self):
        self.assertEqual(MIN_QUALIFYING_GAMES, 3)
        self.assertEqual(
            inspect.signature(fit_adjusted_efficiency).parameters["min_games"].default,
            MIN_QUALIFYING_GAMES,
        )

    def test_snapshot_with_two_d1_games_is_explained(self):
        tab = pd.DataFrame([{
            "Team ID": "2623",
            "adj_o": float("nan"),
            "adj_d": float("nan"),
            "adj_em": float("nan"),
            "games_used": 2,
            "league_games": 1066,
            "method": "Experimental paired D1",
            "Snapshot UTC": self.snapshot,
        }])
        with patch("adjusted_display._read", return_value=tab):
            observed = merge_team_stats(
                self.raw, "2623", "mens-college-basketball",
                before="2026-11-25T23:59:00Z",
            )
        self.assertEqual(observed["adjusted_games"], 2)
        self.assertEqual(observed["adjusted_min_games"], 3)
        self.assertEqual(_adjusted_sample_shortfall(observed), (2, 3))
        for key in ("adj_o", "adj_d", "adj_em"):
            self.assertEqual(_value(observed, key), "2/3 games")
        self.assertEqual(_value(observed, "off_eff"), "115.2")
        self.assertEqual(_value(observed, "tempo"), "68.8")
        self.assertNotIn("adj_o", observed)

    def test_five_qualifying_games_keep_original_numeric_values(self):
        tab = pd.DataFrame([{
            "Team ID": "198",
            "adj_o": 102.2508,
            "adj_d": 101.9092,
            "adj_em": .3416,
            "games_used": 5,
            "league_games": 1066,
            "method": "Experimental paired D1",
            "Snapshot UTC": self.snapshot,
        }])
        with patch("adjusted_display._read", return_value=tab):
            observed = merge_team_stats(
                self.raw, "198", "mens-college-basketball",
                before="2026-11-25T23:59:00Z",
            )
        self.assertIsNone(_adjusted_sample_shortfall(observed))
        self.assertEqual(_value(observed, "adj_o"), "102.3")
        self.assertEqual(_value(observed, "adj_d"), "101.9")
        self.assertEqual(_value(observed, "adj_em"), "0.3")

    def test_invalid_source_does_not_claim_sample_shortfall(self):
        for stats in (
            None, {}, {"validated": False},
            {"validated": True, "adjusted_games": 2, "adjusted_min_games": 3},
            {"validated": True, "adjusted_snapshot": self.snapshot},
            {"validated": True, "adjusted_snapshot": self.snapshot,
             "adjusted_games": float("nan"), "adjusted_min_games": 3},
            {"validated": True, "adjusted_snapshot": self.snapshot,
             "adjusted_games": 2, "adjusted_min_games": 0},
        ):
            self.assertIsNone(_adjusted_sample_shortfall(stats))
            self.assertEqual(_value(stats, "adj_o"), "Not available yet")
        self.assertEqual(_adjusted_sample_shortfall({
            "validated": True, "adjusted_snapshot": self.snapshot,
            "adjusted_games": 2, "adjusted_min_games": 3,
            "adj_o": 102.0,
        }), None)

    def test_no_change_to_minimum_games_or_presentation_layout(self):
        source = Path("efficiency_ui.py").read_text()
        ast.parse(source)
        self.assertIn('st.container(key="cs185_matchup_stats")', source)
        self.assertIn("Adjusted efficiency withheld until at least 3 qualifying D1", source)
        self.assertIn("st.caption('Adjusted efficiency withheld", source)
        self.assertIn("Raw efficiency uses separate eligibility rules", source)


if __name__ == "__main__":
    main()

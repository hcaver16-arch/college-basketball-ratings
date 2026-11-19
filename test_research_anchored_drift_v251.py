"""Regression tests for Courtside V251 time-ordering, anchors and drift."""
from datetime import date
import unittest

import pandas as pd

from rating_engine import blending_weight
from research_anchored_drift_v251 import (
    evaluate_windows, actual_saved_season_drift, record_metrics,
    summarize_historical, to_engine,
)


def fixtures():
    return pd.DataFrame([
        {"game_id":"G1","day":date(2025,11,8),"home_id":"1","away_id":"2",
         "home_points":85,"away_points":61,"venue":"Home"},
        {"game_id":"G2","day":date(2025,11,15),"home_id":"1","away_id":"2",
         "home_points":88,"away_points":65,"venue":"Neutral"},
        {"game_id":"G3","day":date(2025,11,22),"home_id":"2","away_id":"1",
         "home_points":73,"away_points":67,"venue":"Home"},
    ])


def snapshots():
    rows=[]
    for day, gp, current in (
        ("2026-11-02", 0, 10.),
        ("2026-11-03", 1, 9.6),
    ):
        weight=1-blending_weight(gp)
        court=(current-weight*10.)/(1-weight) if gp else float("nan")
        rows.append({"Snapshot date":day,"Team ID":"1",
                     "Preseason rating":10.,"Games played":gp,
                     "On-court rating":court,"Preseason weight":weight,
                     "Current power":current})
        rows.append({"Snapshot date":day,"Team ID":"2",
                     "Preseason rating":-10.,"Games played":gp,
                     "On-court rating":(-current+weight*10.)/(1-weight)
                        if gp else float("nan"),
                     "Preseason weight":weight, "Current power":-current})
    return pd.DataFrame(rows)


class V251Tests(unittest.TestCase):
    def test_replay_uses_only_earlier_dates(self):
        prior={"1":10.,"2":-5.}
        games=to_engine(fixtures())
        windows=[(date(2025,11,7),date(2025,11,14)),
                 (date(2025,11,14),date(2025,11,21)),
                 (date(2025,11,21),date(2025,11,28))]
        preds, drift, folds=evaluate_windows(prior,games,windows=windows)
        self.assertEqual(len(preds),3)
        self.assertEqual([x["training_game_count"] for x in folds],[0,1,2])
        self.assertEqual(preds["game_id"].tolist(),["G1","G2","G3"])
        self.assertEqual(preds.iloc[0]["legacy_blended"],
                         preds.iloc[0]["prior_only"])
        self.assertNotAlmostEqual(preds.iloc[1]["anchored_ridge8"],
                                  preds.iloc[1]["legacy_blended"])
        self.assertTrue(all(preds["target_day"]>=preds["window_start"]))
        self.assertTrue(all(preds["target_day"]<preds["window_stop_exclusive"]))
        self.assertGreater(len(drift),0)

    def test_mutating_holdout_outcome_does_not_change_own_prediction(self):
        prior={"1":10.,"2":-5.}
        windows=[(date(2025,11,7),date(2025,11,14)),
                 (date(2025,11,14),date(2025,11,21))]
        before,_,_=evaluate_windows(prior,to_engine(fixtures()),windows=windows)
        altered=fixtures()
        altered.loc[altered["game_id"]=="G2","home_points"]=140
        after,_,_=evaluate_windows(prior,to_engine(altered),windows=windows)
        for method in ("prior_only","legacy_blended",
                       "anchored_ridge8","anchored_ridge16"):
            self.assertEqual(before.iloc[-1][method],after.iloc[-1][method])

    def test_windows_must_not_overlap(self):
        with self.assertRaises(ValueError):
            evaluate_windows({"1":10.,"2":-5.},to_engine(fixtures()),
                windows=[(date(2025,11,7),date(2025,11,21)),
                         (date(2025,11,14),date(2025,11,28))])

    def test_saved_production_cohorts_and_no_double_count(self):
        out=actual_saved_season_drift(snapshots())
        self.assertEqual(out["teams"],2)
        self.assertEqual(sum(x["teams"] for x in out["cohorts"]),2)
        self.assertTrue(out["latest_snapshot_day"]=="2026-11-03")
        self.assertFalse(out["d1_only"])

    def test_empty_and_overfitted_metrics_not_promoted(self):
        df=pd.DataFrame(columns=["actual_margin","legacy_blended"])
        self.assertIsNone(record_metrics(df,"legacy_blended")["mae"])
        with self.assertRaises(ValueError):
            summarize_historical(df,pd.DataFrame(),[])

    def test_nonunique_historical_fixture_is_rejected(self):
        x=fixtures()
        with self.assertRaises(ValueError):
            to_engine(pd.concat([x,x.iloc[[0]]],ignore_index=True))


if __name__=="__main__":
    unittest.main()

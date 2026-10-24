import unittest
import pandas as pd
from historical_efficiency_test import run_backtest

class TestHistoricalEfficiency(unittest.TestCase):
    def test_strictly_pregame_and_no_mutation(self):
        teams=['1','2','3','4']
        rows=[]
        for d in range(55):
            a,b=teams[d%4],teams[(d+1)%4]
            if a==b:continue
            rows.append({'game_id':str(d),'date':(pd.Timestamp('2025-11-01')+pd.Timedelta(days=d)).strftime('%Y-%m-%d'),
                         'home_id':a,'away_id':b,'home_points':72+(d%3),
                         'away_points':66+(d%4),'possessions':69.})
        source=pd.DataFrame(rows); backup=source.copy(deep=True)
        preds, stats=run_backtest(source,warmup_days=20,step_days=7,min_team_games=2,min_league_games=10)
        self.assertTrue(len(preds)>0)
        for _,r in preds.iterrows():
            self.assertLess(pd.Timestamp(r['training_max_date']),pd.Timestamp(r['forecast_cutoff_utc']))
            self.assertLessEqual(pd.Timestamp(r['forecast_cutoff_utc']),pd.Timestamp(r['date']))
        pd.testing.assert_frame_equal(source,backup)
        self.assertEqual(stats['evaluated_games'],len(preds))
    def test_no_games(self):
        empty=pd.DataFrame(columns=['game_id','date','home_id','away_id','home_points','away_points','possessions'])
        out,summary=run_backtest(empty)
        self.assertTrue(out.empty)
        self.assertEqual(summary['input_games'],0)

if __name__=='__main__':unittest.main()

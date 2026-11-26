import tempfile
import unittest
from pathlib import Path
import pandas as pd
from adjusted_display import select_snapshot

class SnapshotTests(unittest.TestCase):
    def test_cutoff(self):
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for i, stamp in enumerate(['2026-11-24T12:00:00Z','2026-11-25T12:00:00Z','invalid']):
                p = Path(d)/f'{i}.csv'
                pd.DataFrame({'Team ID':['1'], 'Snapshot UTC':[stamp], 'adj_o':[100+i]}).to_csv(p,index=False)
                paths.append(p)
            self.assertEqual(select_snapshot(paths,'2026-11-25T12:00:00Z').iloc[0].adj_o,100)
            self.assertEqual(select_snapshot(paths,'2026-11-25T12:00:01Z').iloc[0].adj_o,101)
            self.assertEqual(select_snapshot(paths).iloc[0].adj_o,101)
            self.assertTrue(select_snapshot(paths,'invalid').empty)
            self.assertTrue(select_snapshot(paths,'2026-11-24T12:00:00Z').empty)

    def test_matchup_wires_both_teams_before_render(self):
        source = Path('matchup_analysis.py').read_text()
        self.assertIn('from adjusted_display import merge_team_stats', source)
        for side, tid in [('away', 'aid'), ('home', 'hid')]:
            call = f'cs_{side}_stats = merge_team_stats(cs_{side}_stats, {tid}, league, before=adjusted_cutoff)'
            self.assertIn(call, source)
            self.assertLess(source.index(call), source.index('        render_matchup_preview(away,home,away_stats=cs_away_stats'))
        self.assertIn('adjusted_cutoff.normalize()', source)

if __name__ == '__main__':
    unittest.main()

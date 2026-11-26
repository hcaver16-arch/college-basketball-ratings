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

if __name__ == '__main__':
    unittest.main()

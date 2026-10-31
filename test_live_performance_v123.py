"""V123 syntax and synthetic data checks; no network or prediction writes."""
import tempfile
from pathlib import Path

import pandas as pd
import live_performance_v123 as v123


def test_valid_rows_and_paired_guard():
    rows = pd.DataFrame([
        {"Game ID": "1", "Game start UTC": "2026-11-01T20:00:00Z",
         "First forecast UTC": "2026-10-31T12:00:00Z",
         "Roster forecast UTC": "2026-11-01T10:00:00Z",
         "Baseline home margin": 5, "Actual home margin": 2,
         "Later roster margin": 4, "Matchup class": "D1 vs D1"},
        {"Game ID": "2", "Game start UTC": "2026-11-01T20:00:00Z",
         "First forecast UTC": "2026-11-01T21:00:00Z",
         "Roster forecast UTC": "2026-11-01T11:00:00Z",
         "Baseline home margin": 1, "Actual home margin": -2,
         "Later roster margin": 3, "Matchup class": "D1 vs D1"},
        {"Game ID": "3", "Game start UTC": "2026-11-01T20:00:00Z",
         "First forecast UTC": "2026-10-31T12:00:00Z",
         "Roster forecast UTC": "2026-11-01T21:00:00Z",
         "Baseline home margin": -1, "Actual home margin": -2,
         "Later roster margin": -3, "Matchup class": "D1 vs D1"},
    ])
    graded, rejected = v123._graded(rows)
    assert rejected == 1
    assert list(graded["Game ID"]) == ["1", "3"]
    assert list(graded["Roster valid"]) == [True, False]
    assert list(graded["Baseline error"]) == [3, 1]
    assert v123._score(graded)["Games"] == 2


if __name__ == "__main__":
    test_valid_rows_and_paired_guard()
    print("V123 synthetic archive checks passed")

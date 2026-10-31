"""Static guard for V127 game-record loading optimization."""
import ast
from pathlib import Path

source = Path("app.py").read_text()
ast.parse(source)
assert 'record_cutoff = min(END, max(START, date.today()))' in source
assert ("get_schedule(SPORTS[league], START, record_cutoff)" in source or
        "_v130_measure('Record history', get_schedule, SPORTS[league], START, record_cutoff)" in source)
assert ("games, failures, truncated, windows_checked = get_schedule(SPORTS[league], first, last)" in source or
        "games, failures, truncated, windows_checked = _v130_measure('Schedule', get_schedule, SPORTS[league], first, last)" in source)
print("V127 schedule-scope checks passed")

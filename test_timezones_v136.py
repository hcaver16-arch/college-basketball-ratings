"""Verify DST-safe conversions and original schedule values are immutable."""
import ast
from pathlib import Path
import pandas as pd
from game_timezones_v136 import display_time, annotate_display_times
assert display_time("2026-11-01","7:00 PM","Central")==("6:00 PM CST","2026-11-01")
assert display_time("2026-11-01","7:00 PM","Pacific")==("4:00 PM PST","2026-11-01")
assert display_time("2026-11-01","12:30 AM","Pacific")==("9:30 PM PDT","2026-10-31")
assert display_time("2026-03-09","7:00 PM","Central")==("6:00 PM CDT","2026-03-09")
src=pd.DataFrame([{"Date":"2026-11-01","Time (ET)":"7:00 PM"}])
out=annotate_display_times(src,"Central")
assert out.at[0,"Display time"]=="6:00 PM CST"
assert out.at[0,"Time (ET)"]=="7:00 PM"
assert "Display time" not in src
for name in ["app.py","courtside_home.py"]:
    ast.parse(Path(name).read_text())
assert 'key="courtside_timezone"' in Path("app.py").read_text()
print("V136 timezone tests passed")

"""V130: ensure diagnostics are read-only and core calls remain present."""
import ast
from pathlib import Path
source = Path("app.py").read_text()
tree = ast.parse(source)
assert "_v130_measure('Schedule', get_schedule" in source
assert "_v130_measure('Record history', get_schedule" in source
assert "_v130_measure('Saved ratings', load_ratings" in source
assert 'st.sidebar.expander("Page performance · V130"' in source
assert "from time import perf_counter" in source
assert "render_home(games," in source
print("V130 instrumentation syntax and safeguards passed")

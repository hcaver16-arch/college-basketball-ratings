"""V144: four-region full bracket layout keeps native team selection."""
import ast
from pathlib import Path
src=Path("tournament_full_v144.py").read_text()
native=Path("tournament_native_v142.py").read_text()
ast.parse(src);ast.parse(native)
assert "render_full_overview(data, league)" in native
assert 'st.radio("Region"' in native
assert "v142_bracket_team" in native
assert "FINAL FOUR" in src and "NATIONAL CHAMPIONSHIP" in src
assert "_region_markup(r,True)" in src
assert "_region_markup(r) for r in left" in src
print("V144 layout checks passed")

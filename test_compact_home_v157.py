"""V157 compact home dashboard structural tests."""
import ast
from pathlib import Path
src=Path("courtside_home.py").read_text()
ast.parse(src)
assert "home_main, home_side = st.columns([1.65, 1], gap='large')" in src
assert "with home_main:" in src and "with home_side:" in src
assert src.index("with home_main:") < src.index("st.markdown('#### All games')")
assert src.index("with home_side:") < src.index("Power rankings")
assert "st.container(height=310,border=True)" in src
assert "st.caption(f\"{len(visible):,} games" in src
assert "courtside_feature_details" in src
assert "courtside_rankings" in src
assert "courtside_requested_page" in src
assert "d1_visible" in src
print("V157 home dashboard checks passed")

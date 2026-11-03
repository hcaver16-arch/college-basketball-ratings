"""V157 compact home dashboard structural tests."""
import ast
from pathlib import Path
src=Path("courtside_home.py").read_text()
ast.parse(src)
assert 'first_row = st.columns(3, gap="small")' in src
assert "with first_row[0]:" in src and "with first_row[2]:" in src
assert src.index("with first_row[0]:") < src.index('st.markdown(\'<div class="cs169-games-title">Today’s matchups</div>\'')
assert src.index("with first_row[2]:") < src.index("Power rankings")
assert "st.container(height=320,border=True)" in src
assert "st.caption(f\"{len(visible):,} games" not in src
assert "courtside_feature_details" in src
assert "courtside_rankings" in src
assert "courtside_requested_page" in src
assert "d1_visible" in src
print("V157 home dashboard checks passed")

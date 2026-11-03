"""V157 compact home dashboard structural tests."""
import ast
from pathlib import Path
src=Path("courtside_home.py").read_text()
ast.parse(src)
assert 'home_columns = st.columns(3, gap="small")' in src
assert "with home_columns[0]:" in src and "with home_columns[2]:" in src
assert src.index("with home_columns[0]:") < src.index('_classic_home_card_heading("Today’s matchups"')
assert src.index("with home_columns[2]:") < src.index("Power rankings")
assert "st.container(height=320,border=False)" in src
assert "st.caption(f\"{len(visible):,} games" not in src
assert "courtside_feature_details" in src
assert "courtside_rankings" in src
assert "courtside_requested_page" in src
assert "d1_visible" in src
print("V157 home dashboard checks passed")

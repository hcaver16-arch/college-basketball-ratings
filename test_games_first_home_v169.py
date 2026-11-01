from pathlib import Path
import ast
s=Path("courtside_home.py").read_text()
ast.parse(s)
assert "cs169-summary" in s
assert "Today’s matchups" in s
assert s.index("cs169-games-title") < s.index("Featured game · Model preview")
assert "st.container(height=260,border=True)" in s
assert "courtside_feature_details" in s
assert "courtside_rankings" in s
assert "with home_side:" in s
assert "cs161-home-header\">" not in s
print("V169 games-first homepage checks passed")

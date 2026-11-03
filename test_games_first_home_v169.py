from pathlib import Path
import ast
s=Path("courtside_home.py").read_text()
ast.parse(s)
assert "cs169-summary" in s
assert "Today’s matchups" in s
assert s.index('_classic_home_card_heading("Today’s matchups"') < s.index("Featured game · Model preview")
assert "st.container(height=320,border=False)" in s
assert "courtside_feature_details" in s
assert "courtside_rankings" in s
assert "with home_columns[2]:" in s
assert "cs161-home-header\">" not in s
print("V169 games-first homepage checks passed")

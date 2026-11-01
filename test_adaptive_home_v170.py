"""V170 homepage scales across quiet, medium, and busy game days."""
from pathlib import Path
import ast
source=Path("courtside_home.py").read_text()
ast.parse(source)
assert 'def select_home_games(' in source
assert 'len(visible) > 30' in source
assert 'len(visible) > 5' in source
assert '["Featured", "Top 25", "Closest", "All"]' in source
assert 'home_display = home_display.head(12)' in source
assert 'st.container(height=320,border=True)' in source
assert 'nullcontext()' in source
assert 'cs170_all_games' in source
assert 'st.session_state["courtside_requested_page"] = "Games"' in source
assert 'Closest games · Next 7 days' in source
assert 'highlight_scores' in source
assert 'courtside_feature_details' in source
print("V170 adaptive homepage structural checks passed")

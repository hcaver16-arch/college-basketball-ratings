"""V160 compact featured matchup regression."""
import ast
from pathlib import Path
s=Path("courtside_home.py").read_text()
ast.parse(s)
assert 'cs160-matchup' in s and 'cs160-predictions' in s
assert 'PROJECTED SPREAD' in s and 'WIN PROBABILITY' in s
assert "f1.metric('Model projected spread'" not in s
assert 'overflow-wrap:anywhere' in s
assert 'courtside_feature_details' in s
assert "st.session_state['courtside_selected_game']" in s
assert "st.container(height=310,border=True)" in s
assert "with home_side:" in s
print("V160 compact matchup verified")

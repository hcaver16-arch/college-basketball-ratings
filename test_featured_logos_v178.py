"""Featured matchup logos respect existing logo preference."""
from pathlib import Path
import ast
s=Path("courtside_home.py").read_text()
ast.parse(s)
assert 'show_feature_logos = st.session_state.get("courtside_logos_enabled", True)' in s
assert 'show_feature_logos and hid.isdigit()' in s
assert 'show_feature_logos and aid.isdigit()' in s
assert '{home_logo}' in s and '{away_logo}' in s
assert 'cs178-feature-logo' in s
assert 'cs160-feature-title' in s
print("V178 featured logos checks passed")

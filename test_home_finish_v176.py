"""V176 logo, navigation, and mobile regression checks."""
from pathlib import Path
import ast
home=Path("courtside_home.py").read_text()
app=Path("app.py").read_text()
ast.parse(home);ast.parse(app)
assert "cs176-logo" in home
assert 'team_id.isdigit()' in home
assert "courtside_logos_enabled" in home
assert 'st.expander("Open a Top 5 team"' in home
assert 'st.session_state["courtside_requested_team"] = name' in home
assert 'st.session_state["courtside_requested_page"] = "Teams"' in home
assert 'st.session_state.pop("courtside_requested_team", None)' in app
assert 'st.session_state["v12_team_pick"] = requested_team' in app
assert "@media(max-width:700px)" in home
print("V176 checks passed")

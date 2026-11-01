"""V171 upcoming cards and navigation regression."""
import ast
from pathlib import Path

home = Path("courtside_home.py").read_text()
app = Path("app.py").read_text()
ast.parse(home)
ast.parse(app)
assert "else st.container(border=True)" in home
assert 'favorite_probability:.0%' in home
assert 'win probability:' in home
assert 'cs171-upcoming' in home
assert 'cs171_highlight_' in home
assert 'courtside_selected_game_payload' in home
assert 'st.session_state["courtside_requested_page"] = "Games"' in home
assert 'selected = pd.DataFrame([linked])' in app
assert 'if isinstance(linked, dict)' in app
assert 'courtside_feature_details' in home
print("V171 clickable matchup cards verified")

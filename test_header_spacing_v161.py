from pathlib import Path
import ast
app=Path("app.py").read_text()
home=Path("courtside_home.py").read_text()
ast.parse(app);ast.parse(home)
assert "cs169-summary" in home
assert "Today’s matchups" in home
assert "cs161-feature-title" not in home
assert "cs160-feature-title" in home
assert "cs169-games-title" in home
assert 'with home_main:' in home and 'with home_side:' in home
assert "settings_panel = st.popover" in app
assert "with st.popover(\"More ▾\"" in app
print("V161 header and spacing checks passed")

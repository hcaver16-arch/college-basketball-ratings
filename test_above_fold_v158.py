from pathlib import Path
import ast
app=Path("app.py").read_text()
home=Path("courtside_home.py").read_text()
ast.parse(app)
ast.parse(home)
assert "padding-top:0.65rem !important" in app
assert "cs169-summary" in home
assert 'cs153-banner cs157-home-banner' not in home
assert "st.container(height=260,border=True)" in home
assert "with home_main:" in home and "with home_side:" in home
assert "courtside_feature_details" in home
print("V158 above-fold compact layout validated")

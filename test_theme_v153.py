"""V153 design-only regression checks."""
from pathlib import Path
import ast
for path in ("app.py","courtside_home.py","courtside_theme_v153.py"):
    ast.parse(Path(path).read_text())
app=Path("app.py").read_text()
home=Path("courtside_home.py").read_text()
theme=Path("courtside_theme_v153.py").read_text()
cfg=Path(".streamlit/config.toml").read_text()
assert "courtside_style()\napply_v153_theme()\napply_table_theme()" in app
assert "st.markdown('### Today’s games')" in home
assert "render_home(games" in app
assert "#2054c5" in theme.lower() and "#08ad9e" in theme.lower()
assert 'base = "light"' in cfg
assert 'primaryColor = "#2054C5"' in cfg
assert "tournament_advancement_v152" not in theme
print("V153 visual-theme integration checks passed")

"""Static safeguard for V126's lazy roster computation."""
from pathlib import Path
import ast

source=Path("app.py").read_text()
ast.parse(source)
assert 'roster_rating_pages = {"Rankings", "Model Lab", "Games", "Teams"}' in source
assert 'if selected_section in roster_rating_pages and isinstance(team_ratings, pd.DataFrame)' in source
assert 'preliminary_ratings = build_preliminary_ratings(' in source
assert 'if selected_section == "Home":' in source
print("V126 page-scoped roster calculation checks passed")

"""Static guard: research-only modules must not load on every Streamlit rerun."""
import ast
from pathlib import Path

tree = ast.parse(Path("app.py").read_text())
research = {"model_testing", "early_season_testing"}
top = [n.module for n in tree.body if isinstance(n, ast.ImportFrom)]
assert not research.intersection(top), "Research imports are still eager"
nested = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module in research}
assert research == nested, f"Missing research imports: {research - nested}"
print("V128 lazy research import checks passed")

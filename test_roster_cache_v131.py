"""V131: confirm cached roster model remains input-keyed and page-scoped."""
import ast
from pathlib import Path

source = Path("app.py").read_text()
tree = ast.parse(source)
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_cached_preliminary_ratings")
assert [a.arg for a in fn.args.args] == ["ratings", "previous", "current", "totals"]
assert any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "cache_data" for d in fn.decorator_list)
assert 'return build_preliminary_ratings(ratings, previous, current, totals)' in source
assert "_v130_measure('Roster adjustments', _cached_preliminary_ratings," in source
assert 'if selected_section in roster_rating_pages' in source
print("V131 caching and page-scoping guards passed")

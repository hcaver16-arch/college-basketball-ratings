"""Check region and details are visible and clickable above the bracket."""
from pathlib import Path
import ast
source=Path("tournament_ui_v140.py").read_text()
ast.parse(source)
assert '<div class="regions" id="regions"></div>' in source
assert source.index('id="detail"') < source.index('id="regions"')
assert "scrollIntoView({behavior:'smooth',block:'start'})" in source
assert "grid-template-columns:repeat(2,minmax(0,1fr))" in source
assert "height=2700" in source
print("V141 layout visibility regression checks passed")

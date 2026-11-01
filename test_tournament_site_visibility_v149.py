"""Check readable labels are actually included in full bracket game markup."""
import ast
from pathlib import Path
src=Path("tournament_full_v144.py").read_text()
ast.parse(src)
assert 'font-size:10px;line-height:1.3;font-weight:600' in src
assert 'white-space:normal;overflow-wrap:anywhere' in src
assert 'min-width:1660px' in src
assert '<small class="venue">'+ "'" in src
assert 'game_site_label(level,region["name"],league)' in src
print("Venue visibility checks passed")

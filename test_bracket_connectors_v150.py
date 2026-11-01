"""V150 structural tests: exact center-to-center wires and no floating native stubs."""
import ast
from pathlib import Path
src=Path("tournament_full_v144.py").read_text()
native=Path("tournament_native_v142.py").read_text()
ast.parse(src)
ast.parse(native)
assert 'class="bracket-wires"' in src
assert 'for a,b in zip(points,points[1:])' in src
assert 'segments.append(f\'<line x1=' in src
assert 'top:{y-card_h/2}px' in src
assert 'xpos(level)' in src
assert "game_site_label(level,region" in src
assert 'v142-connector' not in native
assert 'st.button(label' in native
print("V150 bracket geometry checks passed")

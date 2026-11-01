import ast
from pathlib import Path
a=Path("bracketology_v138.py").read_text()
b=Path("tournament_native_v142.py").read_text()
ast.parse(a)
ast.parse(b)
assert "render_native_bracket(frame)" in a
assert "render_interactive_bracket(frame)" not in a
assert 'st.button(label' in b
assert 'st.session_state["v142_bracket_team"]' in b
assert 'st.radio("Region"' in b
assert 'st.rerun()' in b
assert "for g in data[\"opening\"]" in b
print("Native tournament UI regression checks passed")

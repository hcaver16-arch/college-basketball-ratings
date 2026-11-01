"""V159 compact navigation smoke checks."""
from pathlib import Path
import ast
s=Path("app.py").read_text()
ast.parse(s)
assert 'cs165-brand' in s
assert 'st.segmented_control("Division"' in s
assert 'primary_pages = ["Home", "Games", "Rankings", "Tournament"]' in s
assert 'more_pages = ["Teams", "Conferences", "Schedule strength", "Record strength", "Model Lab"]' in s
assert 'with st.popover("More ▾"' in s
assert 'settings_panel = st.popover("⚙ Settings"' in s
assert 'courtside_mobile_nav' in s and 'courtside_mobile_division_control' in s
assert "selected_section = st.session_state['courtside_page']" in s
assert 'league = st.session_state["courtside_division"]' in s
print("Compact navigation V159 checks passed")

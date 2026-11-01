"""V162 compact header alignment regression."""
from pathlib import Path
import ast
s=Path("app.py").read_text()
ast.parse(s)
assert 'nav_cols = st.columns' in s
assert s.index('cs159-brand') < s.index('with st.container(key="courtside_unified_nav")')
assert 'with nav_cols[5]:' in s and 'with nav_cols[6]:' in s
assert 'st.segmented_control("Division"' in s
assert 'settings_panel = st.popover("⚙ Settings"' in s
assert 'settings_panel.toggle(' in s
assert 'on_change=_persist_logo_preference' in s
assert "courtside_mobile_nav" in s and "courtside_mobile_division_control" in s
assert "selected_section = st.session_state['courtside_page']" in s
print("V162 navigation alignment regression passed")

from pathlib import Path
import ast
s=Path("app.py").read_text()
ast.parse(s)
assert 'with st.container(key="courtside_header_top")' in s
assert 'with st.container(key="courtside_desktop_nav")' in s
assert s.index('with st.container(key="courtside_header_top")') < s.index('with st.container(key="courtside_desktop_nav")')
assert 'with st.container(key="courtside_unified_nav")' not in s
assert 'with division_area:' in s and 'with settings_area:' in s
assert 'settings_panel = st.popover("⚙ Settings"' in s
assert 'settings_panel.toggle(' in s
assert 'st.segmented_control("Division"' in s
assert 'courtside_mobile_nav' in s
assert 'courtside_mobile_division_control' in s
assert 'with st.popover("More ▾"' in s
print("V165 two-row header structure verified")

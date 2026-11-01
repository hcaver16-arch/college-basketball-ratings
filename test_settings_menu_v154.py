"""V154 header settings popover regression checks."""
from pathlib import Path
import ast
source=Path("app.py").read_text()
ast.parse(source)
assert 'st.popover("⚙ Settings"' in source
assert 'st.sidebar.' not in source
assert 'settings_panel.toggle(' in source
assert 'settings_panel.selectbox("Show tipoff times in"' in source
assert 'settings_panel.date_input("Browse date (Eastern)"' in source
assert 'settings_panel.selectbox("Show games for"' in source
assert 'settings_panel.selectbox("Load schedules for"' in source
assert 'settings_panel.button("🔄 Refresh schedule now"' in source
assert 'settings_panel.expander("Page performance · V130"' in source
assert 'key="courtside_timezone"' in source
assert 'key="cs_calendar_span"' in source
assert 'key="courtside_logos_enabled"' in source
assert 'on_change=_persist_logo_preference' in source
assert '[data-testid="stSidebar"]' in source
assert 'courtside_mobile_nav' in source and 'courtside_desktop_nav' in source
print("V154 Settings popover wiring passed")

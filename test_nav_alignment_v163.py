from pathlib import Path
import ast
s=Path("app.py").read_text()
ast.parse(s)
assert 'nav_area, division_area, settings_area = st.columns' in s
assert '.st-key-courtside_desktop_nav button,' in s
assert 'height:38px !important' in s
assert '.st-key-courtside_top_division [data-baseweb="button-group"]' in s
assert 'settings_panel = st.popover("⚙ Settings"' in s
assert 'courtside_mobile_division_control' in s
print("V163 navbar control alignment checks passed")

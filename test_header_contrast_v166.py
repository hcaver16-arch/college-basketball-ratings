from pathlib import Path
import ast
app=Path("app.py").read_text()
home=Path("courtside_home.py").read_text()
ast.parse(app);ast.parse(home)
assert 'button[aria-pressed="true"]' in app
assert 'button[aria-checked="true"]' in app
assert 'color:#153560 !important' in app
assert 'background:#ffffff !important' in app
assert 'settings_panel = st.popover("⚙ Settings"' in app
assert 'st.segmented_control("Division"' in app
assert 'courtside_mobile_division_control' in app
assert 'linear-gradient(110deg,#12306a,#1b469d 72%,#1e78b5)' in home
assert 'cs161-home-header' in home
print("V166 color styling and controls checks passed")

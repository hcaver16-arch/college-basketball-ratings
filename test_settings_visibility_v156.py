import ast
from pathlib import Path
s=Path("app.py").read_text()
ast.parse(s)
assert 'settings_panel = st.popover("⚙ Settings"' in s
assert 'position:fixed !important' not in s
assert 'position:relative !important' in s
assert 'settings_panel.toggle(' in s
assert 'settings_panel.selectbox("Show tipoff times in"' in s
print("V156 settings visibility rollback verified")

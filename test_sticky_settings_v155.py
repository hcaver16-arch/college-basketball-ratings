import ast
from pathlib import Path
source=Path("app.py").read_text()
ast.parse(source)
assert 'with st.container(key="courtside_sticky_settings"):' in source
assert 'settings_panel = st.popover("⚙ Settings"' in source
assert '.st-key-courtside_sticky_settings {' in source
assert 'position:relative !important' in source
assert 'position:fixed !important' not in source
assert 'settings_panel.toggle(' in source
assert 'settings_panel.selectbox("Show tipoff times in"' in source
assert 'st.sidebar.' not in source
print("V155 settings regression checks passed (V156 safe visibility rollback)")

"""V185 style-only matchup comparison checks."""
import ast
from pathlib import Path
source=Path("efficiency_ui.py").read_text()
ast.parse(source)
assert 'st.container(key="cs185_matchup_stats")' in source
assert '.st-key-cs185_matchup_stats {max-width:1120px' in source
assert '.cs-eff-compare-head {background:#173b7b' in source
assert '.cs-eff-compare-row:hover {background:#e6f5f3' in source
assert '@media(max-width:720px)' in source
assert 'justify-self:center;width:100%' in source
assert 'with st.expander(group_title' in source
print("V185 visual comparison checks passed")

import ast
from pathlib import Path
source=Path("tournament_native_v142.py").read_text()
ast.parse(source)
assert '@st.dialog("Courtside team résumé")' in source
assert source.count("_select_team(")==4
assert 'st.rerun()' not in source
assert 'st.session_state["v142_bracket_team"]=name' in source
print("V143 direct-click dialog checks passed")

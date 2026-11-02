"""V187: cards with same status must have distinct Streamlit keys."""
from pathlib import Path
import ast
s=Path("app.py").read_text()
ast.parse(s)
assert 'key=f"cs186_game_{status.lower()}_{game[\'Game ID\']}"' in s
assert 'key=f"cs186_game_{status.lower()}"' not in s
def key(status, game_id):
    return f"cs186_game_{status.lower()}_{game_id}"
assert len({key("Scheduled",str(i)) for i in range(100)})==100
assert key("Scheduled","401")!=key("Final","401")
print("V187 unique game card key check passed")

"""V188: Games status and D1 model eligibility labels."""
from pathlib import Path
import ast
s=Path("app.py").read_text()
ast.parse(s)
for x in ['cs188_matchup_scope','["All games", "D1 vs D1 only"]','"**Non-D1 opponent**"','"**Outside D1 model**"','"**Rating unavailable**"','"Both teams D1 · No model line"','"No model line"','courtside_games_status_v182','game_records(record_schedule, game)','render_matchup(']:
    assert x in s,x
print("V188 Games labels and D1 filter checks passed")

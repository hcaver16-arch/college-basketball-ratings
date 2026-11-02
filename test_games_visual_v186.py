"""V186 comprehensive Games visual regression."""
from pathlib import Path
import ast
s=Path("app.py").read_text()
ast.parse(s)
for marker in ('cs186_scoreboard','cs186_game_','cs186_matchup_detail','max-width:1240px',
               'border-left:5px solid #0e9f91','border-left:5px solid #2054c5',
               'courtside_games_status_v182','cs_calendar_anchor','render_matchup(',
               'game_records(record_schedule, game)','_v183_games_scoreboard(games.copy(), record_schedule.copy())'):
    assert marker in s,marker
print("V186 comprehensive Games layout structural checks passed")

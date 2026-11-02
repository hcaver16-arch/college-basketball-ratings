"""V183 scoreboard integration regression tests."""
import ast
from pathlib import Path
s=Path("app.py").read_text()
ast.parse(s)
assert '@st.fragment(run_every="120s")' in s
assert 'def _v183_games_scoreboard(games, record_schedule):' in s
assert '_v183_games_scoreboard(games.copy(), record_schedule.copy())' in s
assert '_v175_today_scoreboard(SPORTS[league], today_et)' in s
assert 'for table in (games, record_schedule):' in s
assert '"Status", "Home score", "Away score"' in s
assert 'cs183-logo-stack' in s
assert 'courtside_logos_enabled' in s
assert 'page_size = 30' in s
for preserved in ('cs_calendar_anchor','courtside_games_status_v182','NET quadrant filters',
                  'render_matchup(','game_records(record_schedule, game)',
                  'Download filtered games CSV','View matchup →','courtside_selected_game_payload'):
    assert preserved in s, preserved
print("V183 scoreboard integration checks passed")

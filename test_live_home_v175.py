from pathlib import Path
import ast
a=Path("app.py").read_text()
h=Path("courtside_home.py").read_text()
ast.parse(a);ast.parse(h)
assert '@st.cache_data(ttl=90' in a
assert '@st.fragment(run_every="120s")' in a
assert '_v175_today_scoreboard(SPORTS[league], today_et)' in a
assert 'live_games = pd.concat([live_games, live]' in a
assert 'render_home(live_games' in a
assert 'row["Status"] == "Live"' in h
assert 'cs175-live-score' in h
print("V175 homepage refresh and live score checks passed")

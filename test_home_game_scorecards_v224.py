"""V224: homepage scores align with their teams and all status states are honest."""
import ast
import sys
import types
from pathlib import Path
import pandas as pd

sys.modules["streamlit"] = types.ModuleType("streamlit")
from courtside_home import home_game_scoreboard_markup

def sample(status, away_score=None, home_score=None, **kwargs):
    return {
        "Status": status, "Away": "Miami Hurricanes", "Home": "Florida Gators",
        "Away ID": "2390", "Home ID": "57", "Away score": away_score,
        "Home score": home_score, "Display time": "7:00 PM CT",
        "Time (ET)": "8:00 PM ET",
        **kwargs,
    }

# Final scores are individual rows, not a compressed "67–77" string
# with the winner pushed onto a third line.
final = home_game_scoreboard_markup(sample("Final", 67, 77), True)
assert 'cs224-final' in final
assert 'FINAL' in final and 'LIVE' not in final
assert 'class="cs224-score">67</span>' in final
assert 'class="cs224-score">77</span>' in final
assert "67 – 77" not in final
assert final.index("Miami Hurricanes") < final.index(">67</span>") < final.index("Florida Gators") < final.index(">77</span>")
assert final.count("cs224-winner") == 1
assert final.index("cs224-winner") > final.index("Miami Hurricanes")
assert '<span class="cs224-win">W</span>' in final
assert "Score unavailable" not in final
assert "Model: " not in final

away_win = home_game_scoreboard_markup(sample("Final", 81, 72), True)
assert away_win.count("cs224-winner") == 1
assert away_win.index("cs224-winner") < away_win.index("Miami Hurricanes")
assert 'class="cs224-score">81</span>' in away_win

# Ties (even if an upstream feed has one) must not fabricate a winner.
tie = home_game_scoreboard_markup(sample("Final", 70, 70), True)
assert "cs224-winner" not in tie and "cs224-win" not in tie

# Invalid score handling is safe: missing, negative, non-numeric or fractional
# results don't create invented winners or errors.
for away in (None, pd.NA, "-3", "bad", "66.5"):
    missing = home_game_scoreboard_markup(sample("Final", away, 70), True)
    assert "Score unavailable" in missing
    assert "cs224-winner" not in missing

# Live scores are presented in two team rows but no live leader is
# incorrectly marked the final winner.
live = home_game_scoreboard_markup(sample("Live", 19, 25), True)
assert "● LIVE" in live
assert 'class="cs224-score">19</span>' in live
assert 'class="cs224-score">25</span>' in live
assert "cs224-winner" not in live
assert "Score unavailable" not in live
no_live_score = home_game_scoreboard_markup(sample("Live"), True)
assert "Score unavailable" in no_live_score
assert no_live_score.count('class="cs224-score">—</span>') == 2

# Scheduled games retain the current model projection and local display time.
scheduled = home_game_scoreboard_markup(sample("Scheduled"), True, "Florida Gators -4.5")
assert "SCHEDULED" in scheduled
assert "7:00 PM CT" in scheduled
assert "D1 vs D1" in scheduled
assert "Model: Florida Gators -4.5" in scheduled
assert "Score unavailable" not in scheduled
assert 'class="cs224-side">AWAY</span>' in scheduled
assert 'class="cs224-side">HOME</span>' in scheduled
no_line = home_game_scoreboard_markup(sample("Scheduled"), False)
assert "Other matchup" in no_line and "No D1 model line" in no_line

# Logo option follows the global toggle; IDs must be safe numeric strings.
assert final.count('<img class="cs224-logo"') == 2
assert 'a.espncdn.com/i/teamlogos/ncaa/500/57.png' in final
assert '<img' not in home_game_scoreboard_markup(sample("Final", 67, 77), True, show_logos=False)
bad_id = sample("Final", 67, 77)
bad_id["Home ID"] = '7" onerror="alert(1)'
assert 'onerror' not in home_game_scoreboard_markup(bad_id, True)

# External team/status strings are escaped rather than treated as HTML.
bad_team = sample("Final", 50, 51)
bad_team["Home"] = "<script>alert(1)</script>"
safe = home_game_scoreboard_markup(bad_team, True)
assert "<script>" not in safe and "&lt;script&gt;" in safe

home = Path("courtside_home.py").read_text()
app = Path("app.py").read_text()
ast.parse(home)
ast.parse(app)
assert "def home_game_scoreboard_markup(" in home
assert "home_game_scoreboard_markup(" in home
assert "cs224_game_card_" in home
assert "cs224-team-row" in home and "cs224-score" in home
assert "cs224-status" in home and "cs224-winner" in home
assert 'show_logos=st.session_state.get("courtside_logos_enabled", True)' in home
assert 'st.button(\'Details →\'' in home
assert "court_game_" in home and "courtside_selected_game" in home
assert 'st.container(height=320,border=False)' in home
assert 'home_columns = st.columns(3, gap="small")' in home
assert 'render_home(live_games, ratings, team_ratings, d1_ids, league, period)' in app
fn = next(n for n in ast.parse(home).body if isinstance(n, ast.FunctionDef) and n.name == "render_home")
assert len(fn.args.args) == 6
print("V224 responsive home scorecards and score/winner data safeguards passed")

"""V241 homepage featured matchup survives Scheduled -> Live -> Final.

Uses synthetic rows, the same read-only scoreboard markup as Today's matchups,
and no network, Streamlit runtime, or rating modifications.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys
import types

import pandas as pd

sys.modules["streamlit"] = types.ModuleType("streamlit")
from courtside_home import featured_home_selection, home_game_scoreboard_markup


def game(gid, day, home, away, hid, aid, status="Scheduled",
         hs=None, aws=None):
    return {
        "Game ID": str(gid), "Date": day, "Home": home, "Away": away,
        "Home ID": str(hid), "Away ID": str(aid), "Status": status,
        "Home score": hs, "Away score": aws,
        "Venue": "Home", "Display time": "7:00 PM CT",
        "Time (ET)": "8:00 PM ET",
    }


day = "2026-11-16"
g1 = game(901, day, "Florida Gators", "Arizona Wildcats", 57, 12)
g2 = game(902, day, "Duke Blue Devils", "Houston Cougars", 150, 248)
g3 = game(903, day, "Non D1", "Duke Blue Devils", 99999, 150)
rated = {"57": 16.14, "12": 16.98, "150": 18.14, "248": 16.38}
d1_ids = set(rated)
scheduled = pd.DataFrame([g1, g2, g3])

# Morning selection holds one game across reruns; first one is competitive.
first, saved = featured_home_selection(scheduled, rated, d1_ids, "Men's")
assert first is not None and saved["game_id"] == str(first["Game ID"])
assert saved["scope"] == "Men's:2026-11-16"
assert first["Status"] == "Scheduled"
assert "PROJECTED SPREAD" in Path("courtside_home.py").read_text()
assert "SCHEDULED" in home_game_scoreboard_markup(first, True)

# Both games move into the live feed: preserve the chosen Game ID and
# scoreboard's actual scores, not a fresh projected spread.
playing = scheduled.copy()
playing.loc[playing["Game ID"].eq("901"), ["Status", "Home score", "Away score"]] = ["Live", 22, 17]
playing.loc[playing["Game ID"].eq("902"), ["Status", "Home score", "Away score"]] = ["Live", 41, 35]
live, continued = featured_home_selection(playing, rated, d1_ids, "Men's", saved)
assert str(live["Game ID"]) == saved["game_id"]
assert live["Status"] == "Live"
assert continued == saved
markup = home_game_scoreboard_markup(live, True, show_logos=True)
assert "● LIVE" in markup and "FINAL" not in markup
assert ('class="cs224-score">22</span>' in markup or
        'class="cs224-score">41</span>' in markup)
assert "cs224-winner" not in markup  # No premature winner.
assert "PROJECTED SPREAD" not in markup
assert markup.count('class="cs224-logo"') == 2

# First load during live action selects a live rated matchup.
fresh, new_saved = featured_home_selection(playing, rated, d1_ids, "Men's")
assert fresh is not None and fresh["Status"] == "Live"
assert new_saved["scope"] == saved["scope"]

# Persist after final even if another game is live or scheduled.
finished = playing.copy()
finished.loc[finished["Game ID"].eq(saved["game_id"]), "Status"] = "Final"
final, final_key = featured_home_selection(finished, rated, d1_ids, "Men's", saved)
assert str(final["Game ID"]) == saved["game_id"]
assert final_key == saved
final_html = home_game_scoreboard_markup(final, True)
assert "FINAL" in final_html and "● LIVE" not in final_html

# If the saved featured team has no new model power, live/final results
# must still remain visible. No midgame forecast recomputation.
reduced = {k: v for k, v in rated.items()
           if k != str(final["Home ID"])}
kept, _ = featured_home_selection(finished, reduced, d1_ids, "Men's", saved)
assert str(kept["Game ID"]) == saved["game_id"]
assert kept["Status"] == "Final"

# Reset when switching division or calendar date; stale/absent IDs
# cannot pin an unrelated game in a later day.
women, key = featured_home_selection(playing, rated, d1_ids, "Women's", saved)
assert key["scope"].startswith("Women's:")
assert key != saved
tomorrow = scheduled.copy()
tomorrow["Date"] = "2026-11-17"
tomorrow_row, tomorrow_key = featured_home_selection(tomorrow, rated, d1_ids, "Men's", saved)
assert tomorrow_row is not None and tomorrow_key["scope"] == "Men's:2026-11-17"
assert tomorrow_key != saved
stale, regenerated = featured_home_selection(playing, rated, d1_ids, "Men's",
                                              {"scope": saved["scope"], "game_id": "404"})
assert stale is not None and regenerated["game_id"] != "404"

# No fake featured D1 game when the source has no verified rated matchup.
other, none = featured_home_selection(pd.DataFrame([g3]), rated, d1_ids, "Men's")
assert other is None and none is None
empty, empty_key = featured_home_selection(scheduled.iloc[:0], rated, d1_ids, "Men's", saved)
assert empty is None and empty_key is None

# Scores and logos must obey the existing shared renderer's safeguards.
no_logos = home_game_scoreboard_markup(live, True, show_logos=False)
assert "<img" not in no_logos
unknown = live.copy()
unknown["Home score"] = None
no_score = home_game_scoreboard_markup(unknown, True)
assert "Score unavailable" in no_score and "cs224-winner" not in no_score

source = Path("courtside_home.py").read_text()
ast.parse(source)
assert 'st.session_state["cs241_featured_selection"] = feature_selection' in source
assert 'st.html(home_game_scoreboard_markup(' in source
assert 'if feature_status in ("Live", "Final"):' in source
assert 'key="cs223_tile_featured"' in source
assert 'key=\'courtside_feature_details\'' in source
assert 'st.session_state[\'courtside_selected_game\']' in source
assert 'st.session_state[\'courtside_selected_game_payload\']' in source
assert 'show_feature_logos = st.session_state.get("courtside_logos_enabled", True)' in source
print("V241 featured live/final continuity, division/date isolation, scores and logos: PASS")

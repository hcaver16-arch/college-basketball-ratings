"""V208: cached ESPN raw events must reparse into the current game schema.

Regression for reported Nov 2 situation: all men's venue source fields existed
in the live ESPN scoreboard but cached processed rows rendered
"Location not announced" after the UI field was added.
"""
from pathlib import Path
import ast
import pandas as pd
from game_location_v207 import game_location_from_espn, UNKNOWN_LOCATION
from live_matchup_v206 import espn_progress

app = Path("app.py").read_text()
tree = ast.parse(app)

def node(name):
    matches = [f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name == name]
    assert len(matches) == 1, name
    return matches[0]

def is_cached(fn):
    return any("cache_data" in ast.unparse(dec) for dec in fn.decorator_list)

assert is_cached(node("_v208_cached_day_events"))
assert is_cached(node("_v208_cached_today_events"))
assert not is_cached(node("retrieve_day"))
assert not is_cached(node("_v175_today_scoreboard"))
assert "_v208_cached_day_events.clear()" in app
assert "_v208_cached_today_events.clear()" in app
assert 'records.extend(rows)' in app
assert 'pd.DataFrame(records, columns=COLUMNS)' in app
assert '"Game location": game_location_from_espn(event, competition)' in app
assert 'context = conf_label + " · " + location_label' in app
assert 'Venue' in app  # model's categorical Home/Neutral field is untouched.

event = {
    "id": "401911469",
    "date": "2026-11-03T04:00:00Z",
    "status": {"type": {"state": "pre"}},
    "competitions": [{
        "neutralSite": False,
        "venue": {
            "id": "2192", "fullName": "Provident Credit Union Event Center",
            "address": {"city": "San Jose", "state": "CA"}
        },
        "competitors": [
            {"homeAway": "home", "team": {"id": "23", "displayName": "San José State Spartans"}, "score": "0"},
            {"homeAway": "away", "team": {"id": "2636", "displayName": "UTSA Roadrunners"}, "score": "0"},
        ],
    }],
}
# Use app's exact parser without importing/launching Streamlit.
env = {
    "pd": pd,
    "safe_name": lambda t: t.get("displayName") or t.get("name") or "Unknown",
    "broadcast_names": lambda e,c: "Not announced",
    "game_location_from_espn": game_location_from_espn,
    "espn_progress": espn_progress,
    "_v208_cached_day_events": lambda sport, day: [event],
}
for name in ("parse_game", "retrieve_day", "_v175_today_scoreboard"):
    fn = node(name)
    fn.decorator_list = []
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "app.py", "exec"), env)

rows,count = env["retrieve_day"]("mens-college-basketball", pd.Timestamp("2026-11-02").date())
assert count == 1
assert rows[0]["Game location"] == "Provident Credit Union Event Center · San Jose, CA"
assert rows[0]["Venue"] == "Home"
assert rows[0]["Status"] == "Scheduled"

# This is the failure the user experienced: an old parsed row contains
# no location, while the same raw ESPN event has the venue available.
old_parsed = dict(rows[0])
old_parsed.pop("Game location")
assert old_parsed.get("Game location") is None
assert game_location_from_espn(event,event["competitions"][0]) != UNKNOWN_LOCATION

# If parsing changes again, identical cached *raw events* get current fields.
env["parse_game"] = lambda e: {"Game location":"Future parsing feature"}
after_upgrade,count2 = env["retrieve_day"]("mens-college-basketball",pd.Timestamp("2026-11-02").date())
assert count2 == 1 and after_upgrade[0]["Game location"] == "Future parsing feature"

# The 90-second live source cache gets reparsed too.
env["_v208_cached_today_events"] = lambda sport, day: [event]
live_rows = env["_v175_today_scoreboard"]("mens-college-basketball",pd.Timestamp("2026-11-02").date())
assert live_rows[0]["Game location"] == "Future parsing feature"

# Both leagues use the same codepath; no hard-coded home school/arena.
for division in ("mens-college-basketball","womens-college-basketball"):
    observed = game_location_from_espn(event,event["competitions"][0])
    assert observed == "Provident Credit Union Event Center · San Jose, CA"

print("V208: raw-event cache migration, parser version resilience, and sourced men's venue fields passed")

"""V207: ESPN venue names are evidence, Home/Neutral is only a category."""
from pathlib import Path
import ast
from game_location_v207 import game_location_from_espn, display_game_location, UNKNOWN_LOCATION

def event(venue=None):
    return {"venue":venue} if venue is not None else {}
def competition(venue=None):
    return {"venue":venue} if venue is not None else {}

arena={"id":"123","fullName":"T-Mobile Arena",
       "address":{"city":"Las Vegas","state":"NV","country":"USA"}}
assert game_location_from_espn(event(),competition(arena))=="T-Mobile Arena · Las Vegas, NV"
assert game_location_from_espn(event(arena),competition())=="T-Mobile Arena · Las Vegas, NV"
assert game_location_from_espn(event({"fullName":"Backup","address":{"city":"Houston","state":"TX"}}),
                               competition(arena))=="T-Mobile Arena · Las Vegas, NV"
assert game_location_from_espn(event(),competition({"fullName":"Allen Fieldhouse"}))=="Allen Fieldhouse"
assert game_location_from_espn(event(),competition({"address":{"city":"Lawrence","state":"KS"}}))=="Lawrence, KS"
assert game_location_from_espn(event(),competition({"fullName":"Scotiabank Arena","address":{"city":"Toronto","country":"Canada"}}))=="Scotiabank Arena · Toronto, Canada"
assert game_location_from_espn(event(),competition({"fullName":"TBD","address":{"city":"Unknown"}}))==UNKNOWN_LOCATION
assert game_location_from_espn(event(),competition())==UNKNOWN_LOCATION
assert game_location_from_espn(event(),competition({"name":"TBD"}))==UNKNOWN_LOCATION
assert game_location_from_espn(event(),competition({"fullName":"The O2","address":{"city":"London","country":"GB"}}))=="The O2 · London, GB"
assert display_game_location({"Game location":" T-Mobile Arena  ·   Las Vegas, NV "})=="T-Mobile Arena · Las Vegas, NV"
assert display_game_location({"Venue":"Neutral"})==UNKNOWN_LOCATION
assert display_game_location({"Game location":float("nan")})==UNKNOWN_LOCATION
assert display_game_location({"Game location":"tbd"})==UNKNOWN_LOCATION

app=Path("app.py").read_text()
match=Path("matchup_analysis.py").read_text()
ast.parse(app)
ast.parse(match)
assert '"Venue", "Status"' in app  # Keep Home/Neutral model category.
assert '"Game location"' in app
assert '"Game location": game_location_from_espn(event, competition)' in app
assert 'context = conf_label + " · " + location_label' in app
assert 'venue_label + " court"' not in app
assert 'display_game_location(game)' in match
assert "venue + ' court</span>'" not in match
assert 'if "Game location" in table.columns:' in app
assert 'fresh.at[gid, "Game location"] != UNKNOWN_LOCATION' in app
assert 'for col in ("Status", "Home score", "Away score", "Game period", "Game clock", "Game phase"):' in app
print("V207 venue parsing, unknown fallbacks, model classification separation and live refresh verified")

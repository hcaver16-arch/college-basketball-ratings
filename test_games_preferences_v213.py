"""V213: midnight rollover, manually chosen dates and persistent logos."""
from datetime import date, datetime, timezone
from pathlib import Path
import ast
from games_preferences_v213 import calendar_today, rollover_anchor, parse_logo_setting

# 19:30 Central on Nov 2 is already Nov 3 on a UTC-hosted Streamlit server.
utc_evening = datetime(2026, 11, 3, 1, 30, tzinfo=timezone.utc)
assert utc_evening.date() == date(2026, 11, 3)
assert calendar_today("Central", utc_evening) == date(2026, 11, 2)
assert calendar_today("Eastern", utc_evening) == date(2026, 11, 2)
assert calendar_today("Pacific", utc_evening) == date(2026, 11, 2)
assert calendar_today("Arizona", utc_evening) == date(2026, 11, 2)
assert calendar_today("Central", datetime(2026,11,3,7,0,tzinfo=timezone.utc)) == date(2026,11,3)

today=date(2026,11,2)
yesterday=date(2026,11,1)
tomorrow=date(2026,11,3)
assert rollover_anchor(tomorrow,today,None,False) == today  # prior UTC slip
assert rollover_anchor(yesterday,today,None,False) == today
assert rollover_anchor(yesterday,today,yesterday,False) == today
assert rollover_anchor(tomorrow,today,tomorrow,False) == today
assert rollover_anchor(tomorrow,today,today,True) == tomorrow
assert rollover_anchor(yesterday,today,yesterday,True) == yesterday
assert rollover_anchor(tomorrow,today,today,False) == tomorrow  # do not change a selected anchor unexpectedly
assert rollover_anchor(date(2026,11,10),today,None,False) == date(2026,11,10)

for choice in ("0","false","OFF",0):
    assert parse_logo_setting(choice) is False
for choice in ("1","true","on",1,None):
    assert parse_logo_setting(choice) is True

app=Path("app.py").read_text()
ast.parse(app)
for marker in (
    "calendar_today(selected_timezone)", "rollover_anchor(",
    "cs213_calendar_manual", "cs213_calendar_last_today",
    "cs_calendar_today", "on_change=_v213_calendar_chosen",
    "courtside_logo_preference", "on_change=_persist_logo_preference",
    "parse_logo_setting(", "cs213_show_today", "filter_by_ranked_teams",
    'rank_source != "Hide rankings" and rank_lookup',
):
    assert marker in app,marker
print("V213 Games time-zone, calendar and logo preference tests passed")

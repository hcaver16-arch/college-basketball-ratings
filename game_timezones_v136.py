"""Display-only NCAA game time-zone conversion.

Date and Time (ET) stay untouched for ESPN day queries, model calculations,
and historical data. Display values can cross local calendar-day boundaries.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

ZONES = {
    "Eastern": "America/New_York",
    "Central": "America/Chicago",
    "Mountain": "America/Denver",
    "Pacific": "America/Los_Angeles",
    "Arizona": "America/Phoenix",
}
SOURCE = ZoneInfo("America/New_York")

def display_time(game_date, eastern_time, zone="Eastern"):
    if zone not in ZONES:
        raise ValueError("Unsupported time zone")
    try:
        original = datetime.strptime(f"{game_date} {eastern_time}", "%Y-%m-%d %I:%M %p")
        value = original.replace(tzinfo=SOURCE).astimezone(ZoneInfo(ZONES[zone]))
        formatted = value.strftime("%I:%M %p").lstrip("0")
        return f"{formatted} {value.tzname()}", value.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return f"{eastern_time} ET", str(game_date)

def annotate_display_times(games, zone):
    out = games.copy()
    if not {"Date", "Time (ET)"}.issubset(out.columns):
        return out
    converted = [display_time(date, time, zone) for date,time in zip(out["Date"],out["Time (ET)"])]
    out["Display time"] = [item[0] for item in converted]
    out["Display date"] = [item[1] for item in converted]
    return out

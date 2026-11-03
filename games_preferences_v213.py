"""V213 Games preferences: user-zone calendar and persistent logo defaults.

Pure helpers let date-rollover behavior be tested without Streamlit or the feed.
"""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from game_timezones_v136 import ZONES


def calendar_today(zone: str = "Central", now: datetime | None = None) -> date:
    """Return the calendar date for the viewer's selected tipoff-time zone."""
    zone_id = ZONES.get(zone, ZONES["Central"])
    now = now if now is not None else datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("calendar_today requires timezone-aware datetime")
    return now.astimezone(ZoneInfo(zone_id)).date()


def rollover_anchor(anchor: date, today: date, last_today: date | None, manual: bool) -> date:
    """Follow today only if the user has not explicitly navigated elsewhere."""
    if manual:
        return anchor
    if last_today is not None:
        return today if anchor == last_today else anchor
    # Upgrade old sessions created before the explicit follow/manual setting.
    # This corrects a one-day UTC mismatch (including an erroneous 'tomorrow').
    if abs((anchor - today).days) <= 1:
        return today
    return anchor


def parse_logo_setting(raw) -> bool:
    """Default to logos on; only explicit off values disable them."""
    return str(raw if raw is not None else "1").strip().lower() not in {"0", "false", "off"}

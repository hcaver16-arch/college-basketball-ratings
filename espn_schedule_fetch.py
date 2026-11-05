"""Reliable read-only ESPN schedule fetching and failure presentation.

ESPN's scoreboard endpoint is undocumented. No missing games are invented:
failed requests still propagate to schedule coverage diagnostics.
"""
from __future__ import annotations

from datetime import date
from time import sleep

import requests


_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/scoreboard"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 CollegeBasketballDashboard/1.1",
    "Accept": "application/json",
}
_RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}


def fetch_scoreboard_events(sport: str, day: date, *, get=None, pause=sleep):
    """Download one date's raw events, retrying only transient failures.

    403 responses are not retried: they often reflect upstream access policy,
    not temporary network trouble. Streamlit caches only successful returns.
    """
    request_get = get or requests.get
    url = _SCOREBOARD_URL.format(sport=sport)
    params = {"dates": day.strftime("%Y%m%d"), "groups": "50", "limit": 500}
    for attempt in range(3):
        try:
            response = request_get(
                url, params=params, headers=_HEADERS, timeout=25,
            )
            if response.status_code in _RETRYABLE_HTTP_STATUS and attempt < 2:
                pause(0.5 * (2 ** attempt))
                continue
            response.raise_for_status()
            events = response.json().get("events")
            if not isinstance(events, list):
                raise ValueError("Schedule feed did not return a game list")
            return events
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 2:
                raise
            pause(0.5 * (2 ** attempt))
    raise RuntimeError("Scoreboard request exhausted its retry budget")


def split_schedule_failures(failures: list[str], today: date):
    """Separate future-only gaps without hiding failed current/past dates.

    A failure with an unparsable date is considered actionable to avoid
    accidentally suppressing data-integrity warnings.
    """
    past_or_current, future = [], []
    for message in failures:
        try:
            failed_day = date.fromisoformat(message.split(":", 1)[0].strip())
        except ValueError:
            past_or_current.append(message)
            continue
        (future if failed_day > today else past_or_current).append(message)
    return past_or_current, future

"""Regression checks for ESPN schedule retries and honest warnings."""
from datetime import date
from unittest.mock import Mock
import requests
from espn_schedule_fetch import fetch_scoreboard_events, split_schedule_failures

DAY = date(2027, 3, 17)


def response(status, events=None):
    result = Mock()
    result.status_code = status
    result.json.return_value = {"events": events if events is not None else []}
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(str(status))
    return result


calls = []
def temporary_failure(*args, **kwargs):
    calls.append(kwargs)
    return [response(503), response(200, [{"id": "123"}])][len(calls)-1]

pauses = []
assert fetch_scoreboard_events("mens-college-basketball", DAY,
                               get=temporary_failure, pause=pauses.append) == [{"id": "123"}]
assert len(calls) == 2 and pauses == [0.5]
assert calls[0]["params"]["dates"] == "20270317"

for status in (403, 404):
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(1)
        return response(status)
    try:
        fetch_scoreboard_events("mens-college-basketball", DAY, get=forbidden, pause=pauses.append)
    except requests.HTTPError:
        pass
    else:
        raise AssertionError("Forbidden/invalid response must not be silently omitted")
    assert len(calls) == 1

calls = []
def always_timeout(*args, **kwargs):
    calls.append(1)
    raise requests.Timeout("timeout")
try:
    fetch_scoreboard_events("womens-college-basketball", DAY, get=always_timeout, pause=lambda _: None)
except requests.Timeout:
    pass
else:
    raise AssertionError("Network failure must propagate after bounded retry")
assert len(calls) == 3

current, upcoming = split_schedule_failures([
    "2026-11-04: timeout",
    "2027-03-17: 403 Client Error",
    "unknown: malformed failure",
], date(2026, 11, 5))
assert len(current) == 2 and len(upcoming) == 1
assert "2027-03-17" in upcoming[0]
print("V229 ESPN retries, failure propagation, and future-date warning scope passed")

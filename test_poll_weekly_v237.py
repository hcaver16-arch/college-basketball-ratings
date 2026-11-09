"""V237: poll source fetches only once per weekly release window per division."""
from datetime import datetime, timezone
from functools import wraps
from unittest.mock import patch
import sys
import types

fake = types.ModuleType("streamlit")
def fake_cache_data(**kwargs):
    def decorate(fn):
        cache = {}
        @wraps(fn)
        def wrapped(*args):
            if args not in cache:
                cache[args] = fn(*args)
            return cache[args]
        wrapped.clear = cache.clear
        return wrapped
    return decorate
fake.cache_data = fake_cache_data
sys.modules["streamlit"] = fake

import published_polls_v137 as polls

def date_time(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)

# At 19:00 ET = 00:00 UTC after daylight saving ends in November.
assert polls.poll_release_cycle(date_time(2026, 11, 9, 23, 59)) == "2026-11-02"
assert polls.poll_release_cycle(date_time(2026, 11, 10, 0)) == "2026-11-09"
assert polls.poll_release_cycle(date_time(2026, 11, 10, 23)) == "2026-11-09"
assert polls.poll_release_cycle(date_time(2026, 11, 16, 23, 59)) == "2026-11-09"
assert polls.poll_release_cycle(date_time(2026, 11, 17, 0)) == "2026-11-16"
# In March Eastern is UTC-4; Monday 19:00 ET = 23:00 UTC.
assert polls.poll_release_cycle(date_time(2027, 3, 15, 22, 59)) == "2027-03-08"
assert polls.poll_release_cycle(date_time(2027, 3, 15, 23)) == "2027-03-15"

requests_seen = []
class Response:
    def raise_for_status(self): pass
    def json(self):
        return {"rankings": [{"name": "AP Top 25", "date": "2026-11-09",
            "ranks": [{"current": 1, "team": {"id": "1", "displayName": "School A"}}]}]}
def fake_get(url, **kwargs):
    requests_seen.append(url)
    return Response()

with patch.object(polls.requests, "get", side_effect=fake_get):
    with patch.object(polls, "poll_release_cycle", return_value="2026-11-09"):
        for _ in range(5):
            assert "AP Top 25" in polls.fetch_polls("mens-college-basketball")
        assert len(requests_seen) == 1, requests_seen
        polls.fetch_polls("womens-college-basketball")
        assert len(requests_seen) == 2, "Each division requires one source fetch"
        polls.fetch_polls("mens-college-basketball")
        assert len(requests_seen) == 2, "Separate tabs share the cache"
    with patch.object(polls, "poll_release_cycle", return_value="2026-11-16"):
        polls.fetch_polls("mens-college-basketball")
        assert len(requests_seen) == 3, "Next weekly release causes fresh fetch"
        polls.fetch_polls.clear()
        polls.fetch_polls("mens-college-basketball")
        assert len(requests_seen) == 4, "Manual check must bypass cached week"

print("V237 Monday release timing (EST/EDT), weekly caching, division separation and manual check passed")

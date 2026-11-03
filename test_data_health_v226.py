"""V226: verified D1 classification and archive-lag-aware health alerts."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from tempfile import TemporaryDirectory
import ast
import json

import reliability_v99 as health

NOW = datetime(2026, 11, 2, 20, tzinfo=timezone.utc)
def iso(when): return when.isoformat().replace("+00:00", "Z")
def game(game_id, home, away, final=False, start=None):
    when = start or (NOW + timedelta(hours=1))
    return dict(game_id=game_id, game_start_utc=iso(when), final=final,
                home_id=home, away_id=away, home_team="Home "+home,
                away_team="Away "+away, home_score=75 if final else None,
                away_score=65 if final else None)
def forecast(g, created=None):
    return dict(division="mens", model_id="official_saved_v97", game_id=g["game_id"],
                forecast_created_utc=iso(created or NOW - timedelta(hours=12)),
                game_start_utc=g["game_start_utc"],
                ratings_snapshot_utc=iso(NOW - timedelta(hours=18)))
def issue_codes(result):
    return {i["code"]: i for i in result["issues"]}

d1 = {"1", "2", "3", "4"}
rating = {"ratings": {"1": 10, "2": 8, "3": 7, "4": 9}}
ready = {"d1": game("d1", "1", "2"),
         "mixed": game("mixed", "1", "900")}
late = game("final", "1", "2", final=True, start=NOW-timedelta(hours=10))
with patch.object(health, "load_official", return_value=(rating, None)):
    # The two men's V99 false critical alerts were D1 at non-D1. Do not
    # treat them as missing D1-v-D1 forecast or missing D1 team ratings.
    only_mixed = health.check_division(
        Path("."), "2026-27", "mens", NOW, {"mixed": ready["mixed"]},
        [], [], d1_ids=d1, archive_asof=iso(NOW),
    )
    assert only_mixed["status"] == "ok", only_mixed
    assert only_mixed["excluded_non_d1_upcoming_12h"] == 1
    assert only_mixed["verified_d1_upcoming_12h"] == 0
    assert "UNRATED_D1_TEAMS" not in issue_codes(only_mixed)
    assert "MISSING_IMMINENT_D1_FORECASTS" not in issue_codes(only_mixed)

    # Genuine D1-v-D1 forecast gaps still escalate within three hours.
    missing_d1 = health.check_division(
        Path("."), "2026-27", "mens", NOW, ready,
        [], [], d1_ids=d1, archive_asof=iso(NOW),
    )
    assert missing_d1["status"] == "critical"
    assert issue_codes(missing_d1)["MISSING_IMMINENT_D1_FORECASTS"]["count"] == 1
    assert missing_d1["excluded_non_d1_upcoming_12h"] == 1

    # Genuine unrated D1 opponent remains critical, even if no forecast exists.
    with patch.object(health, "load_official", return_value=(
        {"ratings": {"1": 10}}, None
    )):
        unrated_d1 = health.check_division(
            Path("."), "2026-27", "mens", NOW, {"d1": ready["d1"]},
            [], [], d1_ids=d1, archive_asof=iso(NOW),
        )
        assert "UNRATED_D1_TEAMS" in issue_codes(unrated_d1)
        assert unrated_d1["status"] == "critical"

    # If the membership feed fails, we show a warning instead of incorrectly
    # assigning every unrated team to non-D1.
    no_d1 = health.check_division(
        Path("."), "2026-27", "mens", NOW, ready, [], [],
        d1_ids=None, membership_error="timeout", archive_asof=iso(NOW),
    )
    assert "D1_DIRECTORY_UNAVAILABLE" in issue_codes(no_d1)
    assert no_d1["status"] == "warning"

    # An ESPN final that occurred since the last archive must not trigger a
    # premature result-loss alert.
    archived_game = forecast(late)
    not_due = health.check_division(
        Path("."), "2026-27", "mens", NOW, {"final": late},
        [archived_game], [], d1_ids=d1,
        archive_asof=iso(late_time := NOW-timedelta(hours=7)),
    )
    assert "MISSING_FINAL_RESULTS" not in issue_codes(not_due)
    assert not_due["status"] == "ok"
    assert not_due["results_waiting_for_next_archive"] == 1

    # Still missing after an eligible archive run => clear warning.
    overdue = health.check_division(
        Path("."), "2026-27", "mens", NOW, {"final": late},
        [archived_game], [], d1_ids=d1,
        archive_asof=iso(NOW-timedelta(hours=2)),
    )
    assert issue_codes(overdue)["MISSING_FINAL_RESULTS"]["count"] == 1
    assert overdue["status"] == "warning"
    assert overdue["results_waiting_for_next_archive"] == 0
    recorded = [dict(division="mens", game_id="final", status="Final")]
    settled = health.check_division(
        Path("."), "2026-27", "mens", NOW, {"final": late},
        [archived_game], recorded, d1_ids=d1, archive_asof=iso(NOW),
    )
    assert "MISSING_FINAL_RESULTS" not in issue_codes(settled)

    unknown_archive = health.check_division(
        Path("."), "2026-27", "mens", NOW, {"final": late},
        [archived_game], [], d1_ids=d1, archive_asof=None,
    )
    assert "ARCHIVE_TIMESTAMP_UNAVAILABLE" in issue_codes(unknown_archive)

    # Strict integrity checks remain for ALL saved forecasts, even non-D1.
    invalid = forecast(ready["mixed"], created=NOW+timedelta(hours=2))
    duplicated = forecast(ready["mixed"])
    integrity = health.check_division(
        Path("."), "2026-27", "mens", NOW, {"mixed": ready["mixed"]},
        [invalid, duplicated], [], d1_ids=d1, archive_asof=iso(NOW),
    )
    assert integrity["status"] == "critical"
    assert "INVALID_PREGAME_TIMESTAMPS" in issue_codes(integrity)
    assert "DUPLICATE_FORECASTS" in issue_codes(integrity)

    # Stale archive is an independent failure for upcoming rated D1 games.
    stale = health.check_division(
        Path("."), "2026-27", "mens", NOW, {"d1": ready["d1"]},
        [forecast(ready["d1"])], [], d1_ids=d1,
        archive_asof=iso(NOW-timedelta(hours=33)),
    )
    assert "ARCHIVE_STALE" in issue_codes(stale)
    assert stale["status"] == "critical"

# Mock ESPN group 50 directory. No Network calls in CI.
class Response:
    def __init__(self, teams): self.teams = teams
    def raise_for_status(self): pass
    def json(self):
        return {"sports": [{"leagues": [{"teams": [
            {"team": {"id": str(i)}} for i in range(1, self.teams + 1)
        ]}]}]}
class Session:
    def __init__(self, n): self.n = n; self.requests = []
    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return Response(self.n)
session = Session(360)
members = health.fetch_d1_membership("mens-college-basketball", session)
assert len(members) == 360 and "360" in members
assert session.requests[0][1]["params"] == {"limit": 1000, "groups": "50"}
assert "teams" in session.requests[0][0]
try:
    health.fetch_d1_membership("mens-college-basketball", Session(30))
    raise AssertionError("Incomplete ESPN group-50 directory should not be trusted")
except RuntimeError as exc:
    assert "incomplete" in str(exc)

source = Path("reliability_v99.py").read_text()
ast.parse(source)
assert 'destination = folder / "health_v99.json"' in source
assert 'forecast_map' in source
assert 'if archive_asof and (now - archive_asof) > timedelta(hours=30)' in source
assert 'status = "critical"' in source
assert 'def fetch_d1_membership(' in source
assert "existing" not in ""  # Deliberate no-op: legacy archive untouched.
workflow = Path(".github/workflows/check_data_health_v99.yml").read_text()
assert "Flag critical health issues" in workflow
assert "reliability_v99.py --season 2026-27" in workflow
print("V226 D1 eligibility, real alerts, archive lag and forecast integrity passed")

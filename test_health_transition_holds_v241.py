"""V241: V99 respects V227's intentionally held D1 newcomer forecasts.

No live ESPN requests; both divisions use synthetic verified D1 schedules.
The V97 forecaster's explicit newcomer hold remains authoritative.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import reliability_v99 as health
from transition_research_v227 import newcomer_game

NOW = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)
def iso(when):
    return when.isoformat().replace("+00:00", "Z")

def game(gid, home="200", away="201", hours=6, *, final=False):
    return {
        "game_id": gid, "game_start_utc": iso(NOW + timedelta(hours=hours)),
        "final": final, "home_id": home, "away_id": away,
        "home_team": "Home " + home,
        "away_team": "West Florida Argonauts" if away == "2697" else "Away " + away,
    }

def forecast(g, division):
    return {
        "game_id": g["game_id"], "division": division,
        "model_id": "official_saved_v97",
        "game_start_utc": g["game_start_utc"],
        "ratings_snapshot_utc": iso(NOW - timedelta(hours=2)),
        "forecast_created_utc": iso(NOW - timedelta(hours=1)),
    }

def issue_codes(report):
    return {item["code"]: item for item in report["issues"]}

d1 = {"2697", "200", "201", "202"}
held = game("held", home="200", away="2697")
ordinary = game("regular", home="200", away="201")
rated = {"ratings": {"200": 4.0, "201": 2.0, "202": 3.0}}  # 2697 intentionally unrated
assert newcomer_game(held, verified_d1=d1, season="2026-27")
assert not newcomer_game(ordinary, verified_d1=d1, season="2026-27")

for division in ("mens", "womens"):
    with patch.object(health, "load_official", return_value=(rated, None)):
        # Source-confirmed newcomer hold isn't a missing eligible forecast or
        # an unrated D1 *error*, despite D1 classification being verified.
        held_only = health.check_division(
            Path("."), "2026-27", division, NOW,
            {"held": held}, [], [], d1_ids=d1, archive_asof=iso(NOW),
        )
        assert held_only["status"] == "ok", (division, held_only)
        assert held_only["verified_d1_upcoming_12h"] == 1
        assert held_only["forecast_eligible_d1_upcoming_12h"] == 0
        assert held_only["expected_transition_holds_upcoming_12h"] == 1
        assert held_only["excluded_non_d1_upcoming_12h"] == 0
        hold = held_only["expected_forecast_holds"][0]
        assert hold["game_id"] == "held" and hold["held_team_ids"] == ["2697"]
        assert hold["reason"] == "V227_MANUAL_HOLD_PENDING_VALIDATION"
        assert "West Florida" in hold["matchup"]
        assert not any(code.startswith("MISSING_") or code == "UNRATED_D1_TEAMS"
                       for code in issue_codes(held_only))

        # But unrelated rated D1 games without locked forecasts still warn.
        gap = health.check_division(
            Path("."), "2026-27", division, NOW,
            {"held": held, "regular": ordinary}, [], [],
            d1_ids=d1, archive_asof=iso(NOW),
        )
        assert gap["status"] == "warning", gap
        assert issue_codes(gap)["MISSING_UPCOMING_D1_FORECASTS"]["count"] == 1
        assert gap["forecast_eligible_d1_upcoming_12h"] == 1
        assert gap["expected_transition_holds_upcoming_12h"] == 1
        assert "West Florida" not in str(issue_codes(gap)["MISSING_UPCOMING_D1_FORECASTS"])

        # The regular game becomes CRITICAL inside the three-hour window.
        near = game("near", home="200", away="201", hours=1)
        urgent = health.check_division(
            Path("."), "2026-27", division, NOW,
            {"held": held, "near": near}, [], [],
            d1_ids=d1, archive_asof=iso(NOW),
        )
        assert issue_codes(urgent)["MISSING_IMMINENT_D1_FORECASTS"]["count"] == 1
        assert urgent["status"] == "critical"

        # A verified D1 team without ratings *and without a transition hold*
        # remains a genuine critical data-health problem.
        with patch.object(health, "load_official", return_value=(
            {"ratings": {"200": 4.0}}, None
        )):
            missing_rating = health.check_division(
                Path("."), "2026-27", division, NOW,
                {"held": held, "regular": ordinary}, [], [],
                d1_ids=d1, archive_asof=iso(NOW),
            )
            assert issue_codes(missing_rating)["UNRATED_D1_TEAMS"]["count"] == 1
            assert missing_rating["status"] == "critical"

        # Integrity checks are independent: a bad archived forecast must
        # still surface, even if the matchup later falls under a hold.
        corrupt = forecast(held, division)
        corrupt["forecast_created_utc"] = iso(NOW + timedelta(hours=8))
        with_bad_archive = health.check_division(
            Path("."), "2026-27", division, NOW,
            {"held": held}, [corrupt], [],
            d1_ids=d1, archive_asof=iso(NOW),
        )
        assert "INVALID_PREGAME_TIMESTAMPS" in issue_codes(with_bad_archive)
        assert with_bad_archive["status"] == "critical"

        # Independent archive staleness isn't hidden by a transition hold.
        stale = health.check_division(
            Path("."), "2026-27", division, NOW,
            {"held": held}, [], [],
            d1_ids=d1, archive_asof=iso(NOW - timedelta(hours=31)),
        )
        assert "ARCHIVE_STALE" in issue_codes(stale)

        # A verified D1 vs outside-D1 game is not an expected hold.
        mixed = health.check_division(
            Path("."), "2026-27", division, NOW,
            {"mixed": game("mixed", home="999", away="2697")},
            [], [], d1_ids=d1, archive_asof=iso(NOW),
        )
        assert mixed["expected_transition_holds_upcoming_12h"] == 0
        assert mixed["excluded_non_d1_upcoming_12h"] == 1

        # Membership feed failure should NOT silently assert an expected hold.
        unknown = health.check_division(
            Path("."), "2026-27", division, NOW,
            {"held": held}, [], [], d1_ids=None, archive_asof=iso(NOW),
        )
        assert unknown["expected_transition_holds_upcoming_12h"] == 0
        assert "D1_DIRECTORY_UNAVAILABLE" in issue_codes(unknown)

        # Outside the source-confirmed 2026 transition start, no hold applies.
        old_season = health.check_division(
            Path("."), "2025-26", division, NOW,
            {"held": held}, [], [], d1_ids=d1, archive_asof=iso(NOW),
        )
        assert old_season["expected_transition_holds_upcoming_12h"] == 0
        assert issue_codes(old_season)["MISSING_UPCOMING_D1_FORECASTS"]["count"] == 1

print("V241 men's/women's transition holds, genuine gaps, rating errors, and integrity passed")

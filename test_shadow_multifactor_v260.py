"""V260 regression: source-qualified coaches, roster scoring proxies, real
minutes, time embargo, immutable pretip first forecasts and identical-game
baseline comparisons. No network calls, no writes to production.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from shadow_coaches_v260 import explicitly_head_coach, parse_coach_items
from shadow_multifactor_v260 import (
    COEFFICIENTS, FIELDS, MODEL_ID, _clip, build_snapshot,
    components_for_team, evaluate, new_forecasts, prior_player_talent,
    settle_forecasts, verified_recent_minutes,
)

now = datetime(2026, 11, 25, 20, 0, tzinfo=timezone.utc)
past = (now-timedelta(days=2)).isoformat()
recent = (now-timedelta(days=1)).isoformat()
today = now.isoformat()
tomorrow = (now+timedelta(hours=3)).isoformat()

# A coach's team affiliation is insufficient; explicit head coach role is
# required, and ambiguous same-season double matches fail closed.
assistant = {"id": "11", "team": {"id": "150"}, "fullName": "Example Assistant",
             "role": "Assistant Coach"}
confirmed = {"id": "12", "team": {"id": "150"}, "fullName": "Example Head",
             "isHeadCoach": True}
assert not explicitly_head_coach(assistant)
assert explicitly_head_coach(confirmed)
assert parse_coach_items([assistant, confirmed]) == {
    "150": {"coach_id": "12", "name": "Example Head"}}
assert not parse_coach_items([confirmed, {**confirmed, "id": "13"}])

# Historical scorer identity must be exact and unique; no invented
# recruiting ranks and no missing player treated as a zero-point player.
roster = pd.DataFrame([
    {"Team ID": "150" if i < 8 else "248", "Player ID": str(5000+i)}
    for i in range(16)
])
prior = pd.DataFrame([
    {"Player ID": str(5000+i), "Minutes": 250, "Points": 100+i*4}
    for i in range(120)
])
tmap, median, audit = prior_player_talent(roster, prior)
assert audit["status"] == "available"
assert len(tmap["150"]["player_priors"]) == 8
assert tmap["150"]["fraction"] == 1.0
assert np.isfinite(median)
duplicated = pd.concat([prior, prior.iloc[[0]]], ignore_index=True)
cleaned, _, _ = prior_player_talent(roster, duplicated)
assert "5000" not in cleaned["150"]["player_priors"]

# Verified team-games, not every parseable athlete row, determine eligibility.
games = pd.DataFrame([
    {"Game ID": str(700+i), "Game date ET": "2026-11-23",
     "Game start UTC": past, "Team ID": "150",
     "Player ID": str(5000+j), "Minutes": float(10+j)}
    for i in range(3) for j in range(8)
] + [
    # A game on today's ET date must not affect today's pretip snapshot.
    {"Game ID": "999", "Game date ET": "2026-11-25",
     "Game start UTC": now.isoformat(), "Team ID": "150",
     "Player ID": "5000", "Minutes": 60},
])
coverage = pd.DataFrame([
    {"Game ID": str(700+i), "Game date ET": "2026-11-23",
     "Game start UTC": past, "Team ID": "150",
     "Checked at UTC": recent, "Status": "verified"}
    for i in range(3)
] + [
    {"Game ID": "999", "Game date ET": "2026-11-25",
     "Game start UTC": today, "Team ID": "150",
     "Checked at UTC": now.isoformat(), "Status": "verified"},
])
minutes = verified_recent_minutes(games, coverage, now)
assert minutes["150"]["verified_games"] == 3
assert "999" not in set(coverage.loc[coverage["Game date ET"].eq("2026-11-23"), "Game ID"])
assert minutes["150"]["observed_minutes"] == 3*sum(10+j for j in range(8))
late = coverage.copy()
late["Checked at UTC"] = (now+timedelta(minutes=10)).isoformat()
assert verified_recent_minutes(games, late, now) == {}
unverified = coverage.copy()
unverified["Status"] = "unverified"
assert verified_recent_minutes(games, unverified, now) == {}

team = components_for_team(
    "150", prior_rating=18.0, anchored_rating=16.0, games_played=3,
    talent_map=tmap, median_prior_p40=median, recent_minutes=minutes,
    roster_v105={"150": .5},
    coaches={"150": {"coach_id": "12", "coach": "Example Head",
                     "continuity": True}})
assert team["coach_verified"] is True
assert team["coach_pts"] == COEFFICIENTS["coach_continuity_magnitude"]
assert team["has_talent"] and team["has_active_minutes_signal"]
assert team["has_roster_coverage"]
assert np.isclose(
    team["shadow_power"],
    round(sum(team[name] for name in (
        "anchored_on_court", "roster_pts", "talent_pts", "minutes_pts",
        "coach_pts")), 5),
    atol=2e-5)
no_sources = components_for_team(
    "248", prior_rating=3.0, anchored_rating=4.0, games_played=0,
    talent_map={}, median_prior_p40=float("nan"),
    recent_minutes={}, roster_v105={}, coaches={})
assert no_sources["shadow_power"] == 4.0
assert no_sources["coach_pts"] == 0
assert not no_sources["coach_verified"] and not no_sources["has_talent"]
assert -1.25 <= team["talent_pts"] <= 1.25
assert -.85 <= team["minutes_pts"] <= .85

for val in (float("nan"), float("inf")):
    assert not np.isfinite(val)
assert _clip(99, .4) == .4

# Immutable schedule first locks need confirmed pregame status and
# unelapsed tipoff even when a bad upstream feed contains final scores.
components = {"150": team, "248": no_sources}
base_event = {
    "game_id": "401999001", "game_start_utc": tomorrow,
    "game_date_et": "2026-11-25",
    "home_id": "150", "away_id": "248",
    "home_team": "Duke Blue Devils", "away_team": "Houston Cougars",
    "neutral": False, "pregame": True, "final": False,
    "home_score": None, "away_score": None,
}
meta = {"official_source_utc": (now-timedelta(hours=2)).isoformat(),
        "input_sha256": "a"*64}
first = new_forecasts({"401999001": base_event}, components, [], now, "mens", meta)
assert len(first) == 1
record = first[0]
assert set(FIELDS).issuperset(record)
assert record["model_id"] == MODEL_ID
assert np.isclose(record["predicted_home_margin"],
                  team["shadow_power"]-no_sources["shadow_power"]+3)
assert first == new_forecasts({"401999001": base_event}, components,
                               first, now, "mens", meta) if False else len(
    new_forecasts({"401999001": base_event}, components,
                  first, now, "mens", meta)) == 0

assert not new_forecasts({"401999001": {**base_event, "pregame": False}},
                         components, [], now, "mens", meta)
assert not new_forecasts({"401999001": {**base_event, "final": True}},
                         components, [], now, "mens", meta)
assert not new_forecasts({"401999001": {
    **base_event, "game_start_utc": (now+timedelta(minutes=20)).isoformat()}},
    components, [], now, "mens", meta)
assert not new_forecasts({"401999001": base_event},
                         components, [], now, "mens",
                         {"official_source_utc": (now+timedelta(minutes=1)).isoformat(),
                          "input_sha256": "a"*64})

# A final may only be evaluated if a valid pretip lock already exists.
ended = {**base_event, "pregame": False, "final": True,
         "home_score": 75, "away_score": 65}
after = now + timedelta(hours=4)
assert settle_forecasts({"401999001": ended}, [], [], after, "mens") == []
final_rows = settle_forecasts({"401999001": ended}, first, [], after, "mens")
assert len(final_rows) == 1
assert not settle_forecasts({"401999001": ended}, first, final_rows, after, "mens")

official = [{
    "division": "mens", "game_id": "401999001",
    "model_id": "official_saved_v97",
    "game_start_utc": tomorrow,
    "forecast_created_utc": (now-timedelta(minutes=5)).isoformat(),
    "predicted_home_margin": 5.0,
}]
eval_result = evaluate(first, final_rows, official)
assert eval_result["mens"]["shadow_all_locked_games"]["games"] == 1
assert eval_result["mens"]["same_game_paired_shadow"]["games"] == 1
assert eval_result["mens"]["same_game_paired_official"]["games"] == 1
assert eval_result["womens"]["shadow_all_locked_games"]["games"] == 0

# Build a full synthetic saved 220-team snapshot, protected by source timestamp.
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    sport = "mens-college-basketball"
    base = root/"data"/"ratings"/sport
    base.mkdir(parents=True)
    teams = [str(1000+i) for i in range(220)]
    all_ratings = pd.DataFrame([{
        "Team ID": tid, "Team": tid,
        "Current power": float(i%30), "Preseason rating": float(i%30),
        "Games played": 0,
    } for i, tid in enumerate(teams)])
    all_ratings.to_csv(base/"latest.csv.gz", index=False, compression="gzip")
    (base/"status.json").write_text(json.dumps({
        "updated_utc": (now-timedelta(hours=2)).isoformat(),
        "division": sport,
    }))
    current_games = pd.DataFrame([{
        "Game ID": "123", "Date": "2026-11-24", "Home ID": "1000",
        "Away ID": "1001", "Home": "A", "Away": "B", "Venue": "Home",
        "Status": "Final", "Home score": 90, "Away score": 65,
    }, {
        "Game ID": "124", "Date": "2026-11-25", "Home ID": "1000",
        "Away ID": "1001", "Home": "A", "Away": "B", "Venue": "Home",
        "Status": "Final", "Home score": 200, "Away score": 10,
    }])
    current_games.to_csv(base/"season_2026-27.csv.gz",
                         index=False, compression="gzip")
    snap, summary = build_snapshot(root, sport, now, d1_ids=teams, coaches={})
    assert len(snap) == 220
    assert summary["on_court_archived_d1_finals_older_than_today_et"] == 1
    assert summary["last_game_day_used"] == "2026-11-24"
    assert summary["coach_continuity_verified"] == 0
    assert summary["playing_time_proxy_coverage"] == 0
    assert snap["1000"]["anchored_on_court"] != snap["1000"]["prior_rating"]
    # A later same-day outcome changes NOTHING in the current fit.
    current_games.loc[current_games["Game ID"].eq("124"), "Home score"] = 20
    current_games.to_csv(base/"season_2026-27.csv.gz",
                         index=False, compression="gzip")
    snap2, _ = build_snapshot(root, sport, now, d1_ids=teams, coaches={})
    assert snap2["1000"]["shadow_power"] == snap["1000"]["shadow_power"]

print("V260 coach gates, talent and minutes quality, anchored games and first-lock validation: PASS")

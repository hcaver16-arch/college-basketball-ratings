"""V240 regression: historical period separation, exact game/venue joins,
selection accounting, rolling holdouts and read-only candidate choice.
"""
from __future__ import annotations

from datetime import date, timedelta
import numpy as np
import pandas as pd

from research_preseason_scale_v240 import (
    BASELINE, CANDIDATES, END, FOLDS, _origin_score, _selection_decomp,
    _slope, attach_saved_2025_26_venues, audit_season, candidate_forecasts,
    candidate_key, fit_frozen_prior, normalize_paired, verify_collection_status,
    walk_forward,
)

assert candidate_key(1.0, 3.0) == BASELINE
assert len(CANDIDATES) == 12
assert BASELINE in CANDIDATES

# Preseason 2024-25 games: all strictly before the following 2025-26 games.
prior_rows = []
for i in range(1200):
    h = str(100 + i % 45)
    a = str(100 + ((i + 9 + i // 40) % 45))
    if a == h:
        a = str(100 + ((i + 11) % 45))
    prior_rows.append({
        "game_id": str(10000 + i), "date": "2025-01-12",
        "home_id": h, "away_id": a, "home_points": 70 + i % 18,
        "away_points": 60 + i % 12, "possessions": 71.0,
    })
previous = normalize_paired(pd.DataFrame(prior_rows), "prior")
prior = fit_frozen_prior(previous)
assert len(prior) >= 35
assert all(np.isfinite(v) for v in prior.values())
assert max(previous["day"]) < date(2025, 11, 1)

# Five months of source-aligned D1-v-D1 results. The official score
# archive supplies venue labels but no independent verification.
fixtures = []
saved = []
first = date(2025, 11, 1)
for day_offset in range((date(2026, 4, 16)-first).days):
    day = first + timedelta(days=day_offset)
    for slot in range(10):
        gid = str(200000 + day_offset*10 + slot)
        h = str(100 + (day_offset*2 + slot*3) % 45)
        a = str(100 + (day_offset*2 + slot*3 + 16) % 45)
        hp = 60 + ((day_offset*7 + slot*3) % 39)
        ap = 55 + ((day_offset*3 + slot*5) % 34)
        venue = "Neutral" if slot == 9 else "Home"
        row = {"game_id": gid, "date": str(day), "home_id": h,
               "away_id": a, "home_points": hp,
               "away_points": ap, "possessions": 69.0}
        fixtures.append(row)
        saved.append({
            "Game ID": gid, "Date": str(day),
            "Home ID": h, "Away ID": a,
            "Home score": hp, "Away score": ap, "Venue": venue,
            "Status": "Final",
        })
current = normalize_paired(pd.DataFrame(fixtures), "current")
saved = pd.DataFrame(saved)

joined, crosswalk = attach_saved_2025_26_venues(current, saved)
assert crosswalk["exact_game_id_team_score_venue_matches"] == len(current)
assert len(joined) == len(current)
assert (joined["venue"] == "Neutral").sum() > 100

# Wrong scores are never silently accepted as historical venue proof.
bad = saved.copy()
bad.loc[0, "Home score"] += 1
filtered, report = attach_saved_2025_26_venues(current, bad)
assert len(filtered) == len(joined)-1
assert report["unmatched_or_unverified_venue"] == 1
bad2 = pd.concat([saved, saved.iloc[[0]]], ignore_index=True)
try:
    attach_saved_2025_26_venues(current, bad2)
    raise AssertionError("Duplicate source game IDs accepted")
except ValueError:
    pass

fixed = candidate_forecasts(prior, joined)
assert len(fixed) == len(current)
assert set(CANDIDATES) <= set(fixed.columns)
assert fixed["game_id"].is_unique
one = fixed.iloc[0]
assert np.isclose(one["s100_h3"], one["prior_gap"] + 3*one["home_designated"])
assert np.isclose(one["s125_h5"], 1.25*one["prior_gap"] + 5*one["home_designated"])
assert np.isclose(one["s75_h0"], .75*one["prior_gap"])

result, folds = walk_forward(fixed)
assert len(folds) == len(FOLDS)
assert len(result) > 1000
assert result["origin"].nunique() == len(FOLDS)
assert result["game_id"].is_unique
assert all(row["last_training_day"] < row["origin"] for row in folds)
assert (result["last_training_day"] < result["day"].astype(str)).all()
assert result["trained_selected_prediction"].notna().all()
assert set(result["trained_selected_model"]) <= set(CANDIDATES)

# Perturb a held-out Dec 15 score. Nov training stays untouched, so
# Dec candidate selection and prediction for the perturbed game do not change.
changed = fixed.copy()
target = changed[changed["day"] == date(2025, 12, 15)].iloc[0]
changed.loc[changed["game_id"] == target["game_id"], "actual_margin"] += 30
changed_result, changed_folds = walk_forward(changed)
assert changed_folds[0]["selected_on_prior_dates_only"] == folds[0]["selected_on_prior_dates_only"]
assert changed_folds[0]["training_candidate_mae"] == folds[0]["training_candidate_mae"]
for model in CANDIDATES:
    assert np.isclose(
        result.loc[result["game_id"] == target["game_id"], model].iloc[0],
        changed_result.loc[changed_result["game_id"] == target["game_id"], model].iloc[0])

# Training outcome change before Dec cutoff CAN modify training statistics,
# but cannot use results on or beyond the Dec origin.
new = fixed.copy()
nov = new[new["day"] == date(2025, 11, 5)].iloc[0]
new.loc[new["game_id"] == nov["game_id"], "actual_margin"] += 25
_, new_folds = walk_forward(new)
assert new_folds[0]["training_candidate_mae"] != folds[0]["training_candidate_mae"]
assert new_folds[0]["last_training_day"] < new_folds[0]["origin"]

# Game rows can arrive in any order; date-cutoff results stay stable.
shuffled, shuffled_folds = walk_forward(fixed.sample(frac=1, random_state=23))
assert [f["selected_on_prior_dates_only"] for f in shuffled_folds] == [
    f["selected_on_prior_dates_only"] for f in folds]
ref = result[["game_id", "trained_selected_prediction"]].sort_values("game_id").reset_index(drop=True)
got = shuffled[["game_id", "trained_selected_prediction"]].sort_values("game_id").reset_index(drop=True)
pd.testing.assert_frame_equal(ref, got)

decomp = _selection_decomp(result[result["home_designated"] == 1])
assert decomp["games"] > 1000
assert np.isclose(
    decomp["mean_actual_designated_home_margin"],
    decomp["mean_preseason_strength_gap_selection_component"] +
    decomp["assumed_3pt_home_site_contribution"] +
    decomp["mean_remaining_residual"], atol=.0002)
assert _slope(result)["games"] == len(result)

# End-to-end synthetic full run for a real historical stream.
h, cohorts, summary = audit_season(previous, current, saved)
assert len(h) == len(result)
assert len(cohorts) >= 20
assert summary["holdout_games_same_candidates"] == len(h)
assert summary["holdout_first_day"] == "2025-12-01"
assert summary["holdout_last_day"] == "2026-04-15"
assert summary["selection_vs_site_components"]["designated_home"]["games"] > 1000
assert summary["selection_vs_site_components"]["ESPN_neutral"]["games"] > 0
assert summary["holdout_metrics"]["trained_selected_prediction"]["games"] == len(h)
assert summary["prior_2025_26_fixture_coverage"]["not_covered"] == 0

# A season-specific collection ledger is required, not merely a filename.
status = {"season": "2024-25", "sport": "mens-college-basketball",
          "last_completed_date": "2025-04-15",
          "days": {str(date(2024, 11, 1)+timedelta(days=i)): {} for i in range(166)}}
assert verify_collection_status(status, "2024-25", "mens-college-basketball")["dates_logged"] == 166
try:
    verify_collection_status(status, "2025-26", "mens-college-basketball")
    raise AssertionError("Wrong season ledger accepted")
except ValueError:
    pass
try:
    normalize_paired(pd.concat([current, current.iloc[[0]]]), "duplicated")
    raise AssertionError("Duplicate input games accepted")
except ValueError:
    pass
try:
    fit_frozen_prior(previous.iloc[:10])
    raise AssertionError("Insufficient prior fit accepted")
except ValueError:
    pass
print("V240 frozen historical prior, safe site join, selection math and time-ordered validation: PASS")

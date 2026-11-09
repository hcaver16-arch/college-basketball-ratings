"""V239 synthetic regression for chronology, cohort bias, 40-point cap and HCA.

No network access, saved production archive mutation or model promotion.
"""
from datetime import date

import numpy as np
import pandas as pd

from early_season_bias_v239 import (
    CAPS, CANDIDATES, _q, add_cap_candidates, add_context,
    breakdowns, fixed_cap_replay, report_one_division,
)
from early_season_calibration_v238 import compare_chronologically
from prior_transition_research_v229 import normalize

COLUMNS = ["Game ID", "Date", "Home ID", "Away ID", "Home",
           "Away", "Home score", "Away score", "Status", "Venue"]


def game(gid, day, home, away, hscore, ascore, venue="Home"):
    return dict(zip(COLUMNS, (str(gid), day, str(home), str(away),
                               str(home), str(away),
                               hscore, ascore, "Final", venue)))


# Include a complete D1 prior universe for the quartile sensitivity check.
prior = {str(i): float(i - 300) / 10.0 for i in range(200, 470)}
prior["356"] = 18.0
prior["201"] = -10.0
prior["202"] = 4.0
prior["203"] = 0.0
prior["204"] = 7.0
ids = set(prior)

day1 = [game(i + 100, "2026-11-01",
             201 if i % 2 == 0 else 202, 203, 80 + (i % 3), 70)
        for i in range(25)]
day2 = [game(1, "2026-11-02", 356, 201, 120, 45),
        game(2, "2026-11-02", 204, 202, 67, 60, "Neutral")]
day3 = [game(3, "2026-11-03", 356, 203, 70, 72)]
season = normalize(pd.DataFrame(day1 + day2 + day3), "test")
all_games, report, _ = compare_chronologically(prior, season, ids,
                                                date(2026, 11, 3))
assert len(all_games) == len(season) == 28
frame, context = add_context(all_games, season, prior, ids)
assert len(context["prior_2025_26_d1_team_quartile_cutoffs"]) == 3
assert len(frame) == 28
assert frame.prior_opponent_quality_quartile.str.startswith("Q").all()
assert frame.prior_gap_bucket.notna().all()
assert frame["location_bucket"].value_counts()["neutral"] == 1
assert frame["blowout_outcome_bucket"].eq("actual_margin_over_40").sum() == 1
assert set(CANDIDATES) - set(frame.columns) == {"anchored_cap20", "anchored_cap60"}

cap = fixed_cap_replay(prior, season, frame)
assert len(cap) == len(frame)
assert cap["game_id"].is_unique
joined = add_cap_candidates(frame, cap)
assert len(joined) == 28
assert np.allclose(joined["anchored_cap40"], joined["anchored_ridge8"])
assert set(CANDIDATES) <= set(joined.columns)
assert joined["cap_fit_latest_training_day"].dropna().lt(joined.loc[
    joined["cap_fit_latest_training_day"].notna(), "day"]).all()

# Cap settings MUST NOT affect any forecast on the first day, because
# no target-day final may have been included.
first = joined[joined["day"] == "2026-11-01"]
np.testing.assert_allclose(first["anchored_cap20"], first["anchored_cap60"])
# Prior day's 75-point margin creates different cap20/cap60 next-day fits.
third = joined[joined["game_id"] == "3"].iloc[0]
assert not np.isclose(third["anchored_cap20"], third["anchored_cap60"])

# Change a same-day final so it crosses the cap: SAME DAY predictions
# must remain unchanged; later-day cap variants are permitted to respond.
changed = season.copy()
changed.loc[changed["Game ID"].eq("1"), "Home score"] = 65
changed_pairs, _, _ = compare_chronologically(
    prior, changed, ids, date(2026, 11, 3))
new_frame, _ = add_context(changed_pairs, changed, prior, ids)
new_cap = fixed_cap_replay(prior, changed, new_frame)
old2 = cap.merge(frame[["game_id", "day"]], on="game_id")
new2 = new_cap.merge(new_frame[["game_id", "day"]], on="game_id")
for col in ("anchored_cap20", "anchored_cap40", "anchored_cap60"):
    a = old2[old2["day"] == "2026-11-02"].set_index("game_id")[col].sort_index()
    b = new2[new2["day"] == "2026-11-02"].set_index("game_id")[col].sort_index()
    np.testing.assert_allclose(a, b, rtol=0, atol=1e-8)
assert not np.isclose(
    old2.loc[old2.game_id.eq("3"), "anchored_cap60"].iloc[0],
    new2.loc[new2.game_id.eq("3"), "anchored_cap60"].iloc[0])

# Venue change holds team ratings FIXED; no stronger HCA claims permitted.
non = joined[~joined["neutral"]]
neu = joined[joined["neutral"]]
np.testing.assert_allclose(non["legacy_hca0_fixed_rating"],
                           non["legacy_replay"] - 3.0)
np.testing.assert_allclose(non["legacy_hca5_fixed_rating"],
                           non["legacy_replay"] + 2.0)
np.testing.assert_allclose(neu["legacy_hca0_fixed_rating"], neu["legacy_replay"])
np.testing.assert_allclose(neu["legacy_hca5_fixed_rating"], neu["legacy_replay"])

# Signed-error decomposition must be exactly additive on ALL fixtures.
assert np.allclose(joined["actual_minus_preseason_forecast"] +
                   joined["preseason_forecast_minus_legacy"],
                   joined["residual_legacy"])
cohort = breakdowns(joined)
assert len(cohort) > 80
assert set(cohort["model"]) == set(CANDIDATES)
for dimension, part in cohort.groupby("dimension"):
    if dimension == "all_games":
        continue
    base = part[part["model"] == "legacy_replay"]
    assert int(base["games"].sum()) == len(joined), (dimension, base)
assert not cohort[cohort["dimension"] == "blowout_outcome_bucket"].empty

# Validate end-to-end research summary and no D1 membership misclassification.
frame2, segmented, strong, stats = report_one_division(
    prior, season, ids, date(2026, 11, 3))
assert len(frame2) == 28
assert len(segmented) == len(cohort)
assert stats["matched_games"] == len(frame2)
assert stats["non_neutral_intercept_only_hca_sensitivity"]["neutral_games_control_count"] == 1
assert stats["retrospective_cap_outcome_buckets"]["abs_final_margin_over_40"]["games"] == 1
assert stats["disagreement_sufficiency"]["independent_prospective_validation_sufficient"] is False
assert not strong.empty and set(strong["opponent_prior_quality_quartile"]).issubset(
    {"Q1_lower", "Q2", "Q3", "Q4_upper", "prior_unknown"})
# This approximate identity is also validated EXACTLY before rounding above.
np.testing.assert_allclose(
    stats["exact_signed_error_decomposition"]["avg_actual_minus_prior_only"] +
    stats["exact_signed_error_decomposition"]["avg_prior_only_minus_legacy"],
    stats["exact_signed_error_decomposition"]["avg_actual_minus_legacy"],
    atol=1.5e-5)

try:
    add_context(frame, season, prior, {"201", "202"})
    raise AssertionError("Small D1 directory accepted")
except ValueError:
    pass
try:
    add_cap_candidates(frame, cap.iloc[:-1])
    raise AssertionError("Incomplete cap candidate coverage accepted")
except ValueError:
    pass
print("V239 read-only chronology, fixture pairing, context and sensitivity tests PASS")

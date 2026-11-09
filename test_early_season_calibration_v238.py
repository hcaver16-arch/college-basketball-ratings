"""V238 regression: chronology, no lookahead, paired coverage and honest diagnostics."""
from datetime import date

import numpy as np
import pandas as pd

from early_season_calibration_v238 import (
    MODELS, _power, compare_chronologically, ranking_diagnostics,
    states_by_day, strong_win_diagnostics,
)
from prior_transition_research_v229 import normalize

COLS = ["Game ID", "Date", "Home ID", "Away ID", "Home", "Away",
        "Home score", "Away score", "Status", "Venue"]


def game(gid, day, h, a, hs, aws, venue="Home"):
    return dict(zip(COLS, [str(gid), day, str(h), str(a), str(h), str(a),
                           hs, aws, "Final", venue]))


prior = {"356": 18.0, "201": -10.0, "202": 4.0, "203": 0.0, "204": 7.0}
# 25 historical/day-one results enable production's >=20-game current fit.
older = [game(i + 100, "2026-11-01",
              "201" if i % 2 == 0 else "202", "203", 80 + i % 3, 70)
         for i in range(25)]
nov2 = [game("1", "2026-11-02", "356", "201", 120, 45),
        game("2", "2026-11-02", "204", "202", 67, 60)]
nov3 = [game("3", "2026-11-03", "356", "203", 70, 72)]
all_games = normalize(pd.DataFrame(older + nov2 + nov3), "synthetic")
ids = {str(i) for i in range(200, 530)} | {"356"}
empty = all_games.iloc[:0]
models = _power(prior, empty)
assert set(models) == set(MODELS)
for values in models.values():
    assert all(np.isclose(values[t], v) for t, v in prior.items())

pairs, report, states = compare_chronologically(prior, all_games, ids,
                                                 date(2026, 11, 3))
assert len(pairs) == len(all_games)
assert report["matched_d1_games"] == len(all_games)
assert set(report["metrics_same_games"]) == set(MODELS)
nov2_pair = pairs[pairs.game_id.eq("1")].iloc[0]
assert nov2_pair["latest_training_day"] == "2026-11-01"
before = _power(prior, all_games[all_games.Day < date(2026, 11, 2)])
assert np.isclose(nov2_pair["anchored_ridge8"],
                  before["anchored_ridge8"]["356"] -
                  before["anchored_ridge8"]["201"] + 3)

# A changed SAME-DAY margin cannot alter a prediction made for that day.\n# Lower it below the 40-point cap so the next-day anchored fit DOES change.
bigger = all_games.copy()
bigger.loc[bigger["Game ID"].eq("1"), "Home score"] = 65
replay, _, _ = compare_chronologically(prior, bigger, ids, date(2026, 11, 3))
old = pairs[pairs.day.eq("2026-11-02")].set_index("game_id")
new = replay[replay.day.eq("2026-11-02")].set_index("game_id")
for key in MODELS:
    np.testing.assert_allclose(old[key], new[key])
# But subsequent dates may update after the new day's completed games.
assert not np.isclose(
    pairs.loc[pairs.game_id.eq("3"), "anchored_ridge8"].iloc[0],
    replay.loc[replay.game_id.eq("3"), "anchored_ridge8"].iloc[0])

# The exact ordering of CSV rows must not affect replay outcomes.
reordered, _, _ = compare_chronologically(
    prior, all_games.sample(frac=1, random_state=23), ids, date(2026, 11, 3))
pd.testing.assert_frame_equal(pairs, reordered)
through_nov2, _, _ = compare_chronologically(
    prior, all_games, ids, date(2026, 11, 2))
assert "3" not in set(through_nov2.game_id)
try:
    compare_chronologically(prior, all_games, {"356", "201"}, date(2026, 11, 3))
    raise AssertionError("Incomplete D1 directory was accepted")
except ValueError:
    pass
try:
    normalize(pd.concat([all_games, all_games.iloc[[0]]]), "duplicate")
    raise AssertionError("Duplicate game was accepted")
except ValueError:
    pass

wins = strong_win_diagnostics(prior, all_games, states, ids)
assert len(wins) == 1
ill = wins.iloc[0]
assert ill["team_id"] == "356"
assert ill["winning_margin"] == 75
assert ill["capped_winning_margin"] == 40
assert ill["opponent_verified_current_d1"]
assert ill["team_finals_on_day"] == 1
assert ill["legacy_blend_weight_after_day"] > 0
# A strong win does not force a positive power change under the published formula.
assert np.isclose(float(ill["legacy_change_after_day"]),
                  float(ill["legacy_power_after_day"]) -
                  float(ill["legacy_power_before_day"]), atol=0.00011)

# Ranking watchlist uses only verified D1 teams, not opponent ratings.
saved = pd.DataFrame([
    {"Team ID": str(i), "Team": ("Akron" if i == 201 else str(i)),
     "Current power": 100 - i * .01, "Preseason rating": 95 - i * .01,
     "Games played": 1, "On-court rating": 10.0, "On-court weight": .07}
    for i in range(200, 530)
])
saved = pd.concat([saved, pd.DataFrame([{
    "Team ID": "90000", "Team": "Not D1", "Current power": 9000.0,
    "Preseason rating": 0.0, "Games played": 1,
    "On-court rating": 50.0, "On-court weight": .07
}])], ignore_index=True)
top, summary = ranking_diagnostics(saved, prior,
                                    all_games.iloc[:0], all_games, ids,
                                    "mens-college-basketball")
assert len(top) == 25
assert "90000" not in set(top.team_id)
assert summary["akron_case"]["team"] == "Akron"
assert summary["rated_current_d1"] >= 200

print("V238 chronology, no-leakage, matched comparisons, rankings and wins: PASS")

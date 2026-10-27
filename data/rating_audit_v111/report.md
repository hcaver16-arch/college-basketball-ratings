# Courtside V111 — Rating-engine integrity audit

**READ-ONLY. No model, ratings, predictions, or site files changed.**

Source SHA-256: `3e058fea5aaacc0f0a8870ead49fe9a54bfe37054b561e42f2d9ef2bad236adb`

## Observed source rules

- Model fits team strengths using regularized least squares on completed-game scoring margins.
- Non-neutral games receive a fixed 3.0-point home adjustment (source-dependent).
- Final margins are clipped to ±40 points.
- Ridge shrinkage is set to 8.0; ratings are mean-centered after fitting.
- Fewer than 20 eligible final games returns no on-court ratings.
- Preseason priors blend toward on-court ratings: 0 games→0%, 5→35%, 10→65%, 15→85%, 20→95%, 25→100%.
- For teams missing from previous season, code initializes preseason prior at zero.

## Checks

| Check | Observed |
|---|---|
| `expected_three_functions_present` | yes |
| `fixed_home_advantage_three` | yes |
| `blowout_capped_40` | yes |
| `ridge_eight` | yes |
| `minimum_twenty_finals` | yes |
| `prior_zero_for_new_teams` | yes |
| `blend_saturates_by_25_games` | yes |
| `team_id_type_sensitive_indexing` | yes |
| `uses_numeric_linear_solve` | yes |
| `drops_duplicate_game_ids` | yes |

## Review priorities

- Venue: non-neutral games always subtract 3 points; does not distinguish true home from away/unknown venue labels.
- Margin clipping limits blowout influence but makes extreme results indistinguishable beyond 40 points.
- Ridge=8 is a modeling choice; quantify shrinkage and opponent-pool coverage before tuning.
- Absent prior-season teams receive a neutral-zero preseason prior; investigate transitional teams and cold starts.
- Potential Team ID dtype mismatch: indexing str(g[ID]) while tids uses original values; verify upstream type normalization.
- Venue text may contain missing/unknown values; code treats anything other than exactly Neutral as home advantage.
- Only Final-score rows enter on-court fit; ensure incomplete or duplicated results are consistently filtered.

## Saved-rating snapshot health

- **mens-college-basketball:** found 727 records; duplicates=0; nonnumeric=0
- **womens-college-basketball:** found 663 records; duplicates=0; nonnumeric=0

## Relevant repository call sites

- `app.py`: calculate_power=2, make_combined=1
- `daily_ratings.py`: calculate_power=2, make_combined=1
- `rating_engine.py`: calculate_power=1, make_combined=1
- `reconstruct_courtside_v89.py`: calculate_power=1, make_combined=0
- `reconstruct_courtside_v90.py`: calculate_power=1, make_combined=0

## Interpretation and next steps

This is **structural review**, not predictive evidence. The values above were inspected, not optimized.
Next: run controlled, source-timestamp-safe experiments around HCA, ridge, priors and roster inputs; compare on the same pregame games before any live changes.
Note: An off-season saved latest snapshot might reflect prior-season outcomes, not independently verified 2026–27 preseason predictions.


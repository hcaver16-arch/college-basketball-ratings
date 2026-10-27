# Courtside V112 — Historical calibration readiness

**RESEARCH ONLY. No rating, prediction, website, or V97/V109 files altered.**

## Calibration decision

- Historical tuning permitted: **NO**
- Why: No independently validated historical walk-forward dataset, per-game as-of ratings and matching period-correct roster snapshots have been demonstrated by this readiness audit.
- Prospective paired scoring readiness: **NOT YET**
- Cannot rule out feature overlap from current files

## Snapshot audit

| Division | Saved ratings | Existing nonzero roster adjustments | Double-counting warning |
|---|---:|---:|---|
| mens-college-basketball | 727 | 0 | NO NONZERO SAVED ADJUSTMENTS DETECTED; overlap not otherwise ruled out |
| womens-college-basketball | 663 | 0 | NO NONZERO SAVED ADJUSTMENTS DETECTED; overlap not otherwise ruled out |

## Research forecast archives

| File | Found | Rows | Timestamp field |
|---|---|---:|---|
| v97_forecasts | True | 0 | forecast_created_utc |
| v97_results | True | 0 | None |
| v109_pairs | True | 0 | paired_created_utc |

## Planned sensitivity grid (not executed)

- **home_advantage_points:** 2, 2.5, 3, 3.5, 4
- **ridge:** 4, 6, 8, 10, 12
- **margin_cap:** 25, 30, 40, 50
- **blend_full_weight_games:** 15, 20, 25, 30, 35
- **roster_scenario:** as_saved_no_extra, v105_extra_only_if_not_already_counted
- **missing_prior:** missing_as_missing, zero_prior, conference_peer_research_only

## Data requirements before calling any variant better

- Historical game outcomes and source IDs, deduplicated.
- As-of pregame baseline inputs, created before the corresponding tipoff.
- Season-correct roster/player participation known at each relevant prediction timestamp.
- Neutral/home/away venue status explicitly verified; never assume unknown means home.
- Season-separated train/validation/test with team/opponent schedule coverage.
- Compare variants on identical games; report MAE and win accuracy by season/venue and uncertainty.
- Guard against using official saved preseason roster adjustments twice.
- Do not infer an optimal HCA, ridge, cap, blending, or cold-start prior from a single current snapshot.

## Output safety

This run is a diagnostic only. It does not automatically fit model variants or publish a new ranking.

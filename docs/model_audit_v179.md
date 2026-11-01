# Courtside V179 — Read-only model audit (2026-11-01)

## Executive conclusion
**Do not tune or replace production ratings yet.** The live site uses saved daily regularized scoring-margin ratings, not the historical on-court proxy research model. A historical source-availability / leakage-free validation barrier remains open. The latest committed rating and forecast status files still report zero 2026–27 completed games as of the Nov 1 morning snapshot.

## Production prediction trace (confirmed in repository)
1. GitHub Action `.github/workflows/refresh_ratings.yml` runs daily at 12:30 UTC (best-effort schedule), executes `daily_ratings.py --sport both`, then `prediction_archive.py --sport both`, and commits `data/ratings/` and `data/predictions/`.
2. `daily_ratings.py` fits completed 2025–26 results and completed 2026–27 results through `rating_engine.calculate_power`, combines them with `make_combined(...,{})` (empty roster adjustments), and writes `latest.csv.gz`, dated history, and status per division.
3. `app.py` reads those files via `saved_ratings.load_ratings`, installs `Current power` into the active rating lookup, and uses team rating differences plus a 3-point non-neutral home adjustment to generate site model lines.
4. `app.py.game_projection` uses normal-CDF approximation with 11-point scale for displayed win probability; it is an *assumed* scale, not demonstrably fitted or calibrated.
5. `preliminary_model.py` computes a separate experimental roster scenario only on selected pages; the saved baseline and daily ratings workflow do **not** incorporate roster effects. `prediction_archive.py` stores first-before-tipoff forecasts and later outcomes separately.

## Rating mechanics (source confirmed)
- At least **20** eligible completed games are needed before an in-season on-court fit is returned; 1 completed game **cannot yet alter the on-court rating component** in the daily engine.
- Regularized least squares with ridge **8.0**, blowout margin clipped to **±40**, fixed non-neutral venue adjustment **3.0** points, mean-centered ratings.
- Preseason influence phaseout: 0/5/10/15/20/25 games → on-court weights 0%/35%/65%/85%/95%/100%; unrepresented teams receive a zero preseason prior once fit is available.
- For a first game, team records can update, but **the rating itself will not yet update through the saved on-court fit** until enough total completed games are available. Do not describe immediate rating movement from one result as verified.

## Latest committed 2026–27 status (not a live scoreboard)
| Division | Snapshot | Current finals | Teams | Archived forecasts | Evaluated forecasts |
|---|---|---:|---:|---:|---:|
| Men's | 2026-11-01 | 0 | 727 | 793 | 0 |
| Women's | 2026-11-01 | 0 | 663 | 788 | 0 |

Sources: `data/ratings/*/status.json` and `data/predictions/*/status.json`. These snapshots precede any later game results and do not establish current live results.

## Findings by severity
**P1 — rating-update timing:** `calculate_power` returns an empty in-season fit before 20 completed games; despite record updates, early outcomes cannot move saved baseline power ratings. The user should see that distinction documented on site rather than assume every final changes rating.

**P1 — historical evaluation not validated for tuning:** `data/walkforward_audit_v113/report.md` found zero verified timestamp-safe pre-tipoff feature rows, and explicitly disallowed historical hyperparameter tuning on available evidence. Prior historical accuracy snapshots are research signals, *not* verified production comparisons.

**P2 — prediction calibration:** The 11-point win-probability scale and 3-point home-court adjustment are source constants, not established current-season calibration. Evaluate against archived first-forecast timestamps and actual results when sufficient samples accrue.

**P2 — alternative models not deployed:** Earlier on-court proxy research and experimental roster scenarios are not the production saved-rating baseline. No justified conclusion yet that swapping them into the website would improve prospective results.

**P2 — source / ID / venue integrity:** `data/rating_audit_v111/report.md` flags type-sensitive team ID construction and 'anything not exactly Neutral = home'. Verify ID normalization and venue provenance in a focused test before changing model output.

**P2 — workflow freshness:** GitHub scheduled cron is not guaranteed at an exact time. Live scoreboard rendering updates faster than saved **daily** power ratings; the UI should distinguish them. Changes to an already-produced forecast must never overwrite immutable pregame archives.

## Recommended sequence (no production algorithm changes in V179)
1. Build deterministic tests for 0, 1, 19, 20, 25 games, including normalized team IDs, venue treatment, correct prior weights and no future games.
2. Add transparent saved-rating snapshot timestamp / game-count indicators to Model Lab or Ratings so score freshness is not confused with power-rating freshness.
3. Audit archived first-forecast vs start-time, lock status, and final-result matching; report paired MAE, winner accuracy, calibration only on identical, timestamp-valid games.
4. Once a robust sample accumulates, compare baseline, historical proxy, and roster scenario chronologically using the exact same matches and data availability cutoffs. Never tune on the evaluation period.
5. Only then propose a separate, reversible model-change PR with before/after measurements.

**Scope:** This audit inspects repository source code and saved status/report artifacts; no workflows were executed and no live-game result was independently validated. No production ratings, prediction formulas, or website UI have been changed.

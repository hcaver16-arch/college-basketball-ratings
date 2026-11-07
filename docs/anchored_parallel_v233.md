# V233 — Parallel preseason-anchored forecast experiment and rating movement labels

## Scope

*Research only.* Official power ratings, the existing margin formula, the 40-point blowout cap, the +3 home advantage, the official baseline model ID and previously locked forecasts remain **unchanged**. A team whose rating falls relative to preseason is not necessarily weaker than yesterday.

This feature adds a second, exactly reproducible candidate rating based on the V229 preseason-anchored ridge fit (ridge 8), backed by the saved 2025–26 previous-season finals and observed 2026–27 finals. It uses **only pre-existing team priors**; teams without a real 2025–26 rating are not given an invented neutral prior. Its predictions are unvalidated, not public betting advice.

## How genuinely pregame comparisons work

The existing **Archive pregame forecasts and outcomes V97** workflow generates a research snapshot **before** calling the V97 immutable first-forecast recorder. The candidate file is `data/prospective/experimental_ratings/{division}/latest.csv.gz`, with `model_id=anchored_ridge8_v233`, its creation UTC, original official snapshot timestamp and SHA-256 hashes of the exact official/current/previous source files.

`prospective_archive_v97.load_optional` already accepts a dated optional experiment. V233 adds a fail-closed source-identity check, so a candidate created against an older official dataset cannot silently generate a new prediction after the official ratings are updated. It can only lock a forecast at least 30 minutes before a scheduled game and within the forecast horizon. Forecast keys are unique by division, game and model. No completed game ever receives a newly reconstructed experimental pregame forecast; existing original forecasts are never replaced.

`paired_anchor_eval_v233.py` reads the same immutable V97 `forecasts.csv` and `results.csv`, requires both models on the **same fixture**, verifies both forecast snapshots precede creation and both creation times precede tipoff, and excludes pairs locked more than six hours apart. Its result files, `anchored_pairs_v233.csv` and `anchored_evaluation_v233.json`, contain the two errors for the **identical graded games**, mean absolute error, RMSE, winner accuracy, signed error and the informative subset whose predictions differ by more than 0.05 points. No comparisons are backfilled before installation. The report marks fewer than 100 informative games as insufficient for selecting a model.

The V97 workflow runs twice daily; the V109 paired-roster workflow still runs independently, but the experiment has its own model ID and cannot alter the V109 roster experiment. A source generation error is nonblocking to the official V97 archive; V233 provenance validation rejects stale candidates. The experiment does not update player recruiting estimates or roster signal weights.

## Clearer website movement labels

The original `Rating change = Current power - Preseason rating` is now consistently displayed as **Vs preseason**, and separate **Since [previous saved snapshot date]** is derived only from genuine dated power snapshots (currently from `data/ratings/{division}/history.csv.gz`). No fabricated per-game changes, no change when history is incomplete, and no model change.

On rankings, both movements appear on Tiles and Compact list. Team pages show both in Overview and Ratings, alongside the existing complete rating trend graph. D1 ranking membership and site-wide logo defaults are unchanged.

On **Model Lab → Performance**, a compact read-only comparison shows paired graded game count, official margin MAE, anchored margin MAE, and the **informative-game** total from the stricter V233 pairing report. The existing V98 model selector can also inspect the individual experimental model, while the official model stays selected by default.

## What happens after merging?

Run the existing **Archive pregame forecasts and outcomes V97** workflow on main to produce the first anchored snapshot and lock **future**, not already-played, candidate predictions. Regular twice-daily V97 runs continue adding new pregame pairs automatically. Check the run summary and `data/prospective/2026-27/anchored_evaluation_v233.json` to see coverage grow. The official model is not promoted automatically, regardless of the early results. Evaluate predictive performance at the January 1 checkpoint, or earlier only if independent future data warrant a deliberate change.

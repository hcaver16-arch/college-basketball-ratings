# Courtside V244 — historical calibration comparison

**Research only.** No live ratings, forecasts, published predictions, or model coefficients change.

Run GitHub Actions → **Courtside V244 historical calibration research** → **Run workflow** after merging. The manual job regenerates the existing V240 and V239 evidence from saved repository data, then writes `data/research_comparison_v244/summary.json` into a downloadable Actions artifact. Pull-request runs execute regression tests only.

## What can be compared
- **V240:** Fixed prior scale 1.0 / 1.25 / 1.5 at assumed 3-point home intercept, plus its previously selected candidate, scored on the *same 2025-26 month-forward holdout games*. A frozen 2024-25 prior is used. The baseline is `s100_h3`.
- **V239:** Anchored ridge-8 cap 20 / 40 / 60, scored on the *same 2026-27 date-before retrospective fixtures*. The baseline is `anchored_cap40`. Each day's outcomes are excluded until after that day's forecasts.
- Separate men's and women's summaries; MAE, change in MAE versus each study's baseline, winner accuracy, signed home-margin bias, and sample counts.
- Actual >40-point blowout slices are **post-result diagnostics only**, not known pregame.

## What cannot be inferred
V239 and V240 are different seasons and different model families. Their MAEs **cannot be ranked against each other**. V239 replays are not official timestamp-locked forecasts. The 2025-26 V240 venue labels are not independently verified. These hypotheses were selected after seeing early 2026-27 results, so the historical studies are exploratory, not an independent untouched validation set. No calibration or home-court change is recommended automatically. Preserve January 1 prospective evaluation.

The script refuses incomplete candidate columns, duplicate IDs, time-order violations, and V239 cap40 reference drift. It writes only to `data/research_comparison_v244/` in the repository, or an explicit external output path.

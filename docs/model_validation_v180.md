# Courtside V180 — Model validation checkpoint

This change adds **automated read-only validation**, not a new rating system.

Run `python validate_model_v180.py`, or open the `V180 model validation (read-only)` GitHub Actions workflow and choose **Run workflow**.

## Tested
- At 0, 1, and 19 completed games the current engine returns no in-season fit. At 20 and 25 it produces ratings.
- Only final-score rows contribute; duplicated game IDs are counted once; scheduled games never enter the fit.
- Preseason/in-season blend follows the existing 0, 5, 10, 15, 20, 25-game anchors, including a numerical example.
- First-forecast archives for men and women must contain unique game IDs, valid timestamps, and forecasts strictly before tipoff.
- A diagnostic probes team-ID type sensitivity and records that unknown venues currently receive the 3-point home adjustment.

## Interpretation
The 20-game minimum, fixed 3-point home advantage, and 11-point win-probability scale are existing design assumptions, not new recommendations. Passing structural checks **does not prove prediction accuracy or probability calibration**. Full historical walk-forward calibration still requires pre-tipoff data provenance and sufficient same-game comparisons.

If an archive check fails, inspect the printed counts and investigate the rows; do not overwrite or retroactively repair archived forecasts without preserving the original evidence.

No code in the engine, site, predictions, or ratings is changed by V180.

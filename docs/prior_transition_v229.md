# Courtside V229 — Investigate early-season preseason strength anchoring

## Question

Why can a 120–45 Illinois win lower its current team rating?

The current production approach independently fits a current-season, zero-centered, ridge-shrunk power rating and blends it with the previous-season power by number of games played (0: 0%, 5: 35%, 10: 65%, 15: 85%, 20: 95%, 25+: 100%). A single game can produce an in-season estimate near zero even if the team has a strong prior. The margin is capped at ±40 points, and a nonneutral home site subtracts 3 points during fitting. This can pull ratings toward zero after a lopsided win. The direction of movement is not necessarily evidence the team performed poorly.

## Three predeclared research alternatives

The V229 analysis compares games in the 2026–27 **saved** season results archive against identical held-out completed D1 matchups:

1. **Prior only**: 2025–26 previous-season power.
2. **Current (legacy) blend**: zero-centered current-season ridge (8) fitted on all finals from earlier calendar days, plus the actual original 0–25-game weighting curve.
3. **Prior-anchored ridge (8)**: directly fit the new scores with preseason ratings as the penalty anchor, solving (L+8I)·strength = score-margin b + 8·prior.

All models use the same 40-point capped result margins and 3-point fixed home court. Opponents of non-D1 schools may enter the training fit, as in existing production, but comparisons only include verified D1-v-D1 games when both had preseason ratings. Missing entrants are not guessed.

## No lookahead

The script groups each target date (Eastern), then trains from **final games on strictly earlier dates only**. Every game on the target date is held out, regardless of tip-off time; this is deliberately conservative and not equivalent to real immutable game-time locks. The same team matchups and scoring outcomes evaluate all three alternatives, avoiding incomparable denominators. It reports margin MAE, RMSE, winner accuracy, signed bias, first-game subsets, and retrospective Illinois diagnostics.

This is a *retrospective day-before replay*, not a first-forecast prospective model. It uses dates from archives known by the research run, not independently witnessed final-availability timestamps, and the saved 2026–27 archive may be stale. A historical venue flag is drawn from saved ESPN scoreboard data, not a separately verified arena source. Early results have small samples; require at least 100 common games for a descriptive signal. Still reserve future unseen contests and independently locked predictions for a fair decision.

## Workflow / scope

Run GitHub Actions > **V229 research - preseason anchor versus current blend**. The pull request automatically runs tests and the replay and saves an artifact. After merging, it can run manually or weekly on Mondays. Only data/research_prior_transition_v229 is written on main.

V229 does **not** modify rating_engine.py, daily_ratings.py, app.py, saved ratings, roster evidence, model lines, or immutable prospective forecasts. No new coefficients are deployed based on exploratory results. January 1, 2027 remains the model-review checkpoint.

**Known limitation:** As of November 5, a daily ratings-refresh workflow failed during women's prediction diagnostics. The main saved-rating snapshots were still dated November 3. V229 reports that snapshot date and does not conceal or repair the failure.

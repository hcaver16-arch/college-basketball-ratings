# V235 — Evaluate preseason roster evidence without changing Courtside ratings

## Purpose

Investigate whether last season's team power ratings, carried directly into preseason, become more predictive when adjusted by documented returning players and incoming transfers. Official daily ratings do NOT apply numerical roster effects. V235 will not change that until validated with independently recorded future predictions.

## Fixed candidates

**Baseline:** 2025–26 prior season scoring-margin strength, the original Courtside preseason rating, with the existing 40-point margin cap, +3 home-court treatment, ridge 8 and full opponent network.

**Roster scenario:** The same baseline plus the V105 experimental roster-continuity sensitivity value (bounded ±2 points). V105 was generated October 27, 2026, before the 2026–27 season. This numerical relationship is a **fixed, untrained assumption**, not an estimated player-impact coefficient. V105 itself builds a relative mix of documented returning minutes and previous-season experience for cross-school exact-ID matches. It does not verify incoming students' final enrollment, eligibility or true talent.

Eligibility for a roster-adjusted game requires both teams to be verified D1, each with ≥8 previous and current roster members, ≥65% linked player-origin coverage, ≥65% confidence, a complete ESPN historical boxscore flag, valid prior returning-minute data and a plausible source adjustment between −2 and +2. A team without enough evidence is not given a made-up penalty or bonus; it retains its unchanged baseline in the descriptive rankings and is omitted from the paired evaluation. This excludes D2-transitioning programs with missing 2025–26 D1 priors.

## Two separate evidence levels

**Retrospective game scoring** uses the pre-season V105 and 2025–26 sources to score already observed 2026–27 finals. It is shown only as exploratory model research, never falsely labeled locked pregame results. Although V105 existed in October, the choice to examine it in V235 came after some games; player identities are ESPN-sourced and not independently verified at the time of each game. Every model is graded on the identical matchup pool.

**Prospective pairing** starts after merging. A separate scheduled or manual GitHub Action records both frozen preseason-only predictions for each eligible future game, with a real forecast-creation UTC timestamp at least 30 minutes before scheduled tipoff, immutable source SHA-256 and roster evidence date. Completed results are appended separately; no model predicts any past game after its score is known. Existing first forecasts and score archives remain untouched. On repeat runs a previously stored game/model forecast is never recomputed. Source files that change require a new model ID rather than silently altering the experiment.

The future comparison reports matched games, games where the two models actually disagree by >0.05 points, MAE, RMSE, win-pick accuracy and signed bias. Fewer than 100 prospectively graded informative games cannot support model selection, and even 100 are not definitive without uncertainty and cross-division checks.

## Current limitations

- V105's underlying October 2026 ESPN roster matches cover many schools but contain ambiguous origin cases; matching exact IDs does not prove verified transfer enrollment.
- Independently reconciled source coverage in V204 encompasses only selected men's teams and has qualified just 12 teams as of November 9. It does not independently cover Division I men's and women's rosters.
- Recruiting class rankings, true transfer impact, injuries, projected lineup minutes, and coaching changes are **not** yet given arbitrary numerical weights.
- A weak-conference or inflated last-season baseline can remain inflated despite roster adjustment; this experiment isolates the incremental roster signal and does not validate every other part of preseason power.
- Retrospective results are insufficient for selecting a model. Keep an unseen prospective holdout; do not change official preseason rankings, existing forecasts, or live model until validated.

## Run and inspect

On PR, Actions → **V235 preseason roster validation and prospective comparison** runs synthetic safety tests and uploads retrospective research rankings and game-level comparison artifacts.

After merge, run that workflow once on the main branch to start collecting immutable forward-looking pairs, then it runs twice daily. Research output is written only under data/preseason_research_v235. The read-only Model Lab performance view can display the independent evidence as it grows. No official model or forecast promotion is automatic.

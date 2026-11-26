# Courtside V260 — multifactor shadow rating (research-only)

**Objective:** run a separate men's and women's NCAA D1 rating/forecast candidate while preserving existing Courtside rankings and the January 1, 2027 evaluation plan.

## Four components and their evidence

| Signal | Method | Evidence / limitation |
| --- | --- | --- |
| Actual on-court play | Ridge-8 opponent-adjusted game-margin fit anchored to saved preseason ratings | Uses only completed ESPN results dated strictly earlier than today's Eastern date; cap 40 |
| Roster scoring experience | Prior-year PTS/40 of players identified on current rosters | Exact unique ESPN player IDs, >=100 previous-year minutes, >=5 sourced players and >=50% roster coverage; max ±1.25 pts. **Not recruiting stars or all-around player value** |
| Actual playing time | The last five verified team-box scores, weighting qualified prior player PTS/40 by actual logged minutes | >=3 completed games and >=60% known historical talent share of minutes; max ±0.85 pts; never impute unknown players as zero |
| Coaching | Explicit verified head-coach ID continuity between 2025–26 and 2026–27 | ESPN catalog must explicitly mark one unambiguous head coach per team per season. ±0.20 hypothetical continuity/transition adjustment; if unverified, no adjustment. **Not coach quality** |
| Additional frozen roster-continuity research | Small portion of V105 returning minutes / transfer-participation research proxy | Requires >=65% confidence and origin coverage; max ±0.40 and fades by game 20. It is untrained and not proof of transfer eligibility |

The **recruiting ranking gap** is not magically filled: reliable historical recruiting or star data have not yet been integrated. Previous-year scoring rates are a narrow proxy for roster experience, not proof of true talent. The coaching component will remain inactive for any team without explicit supported evidence. Each snapshot exposes feature coverage, so uncertainty is visible.

All weights are fixed untrained hypotheses. Changing these weights must use a NEW model version/ID, not overwrite earlier records. No parameters have been learned from the current season's match outcomes.

## No-leakage and independent archiving guarantees

- Official saved source ratings are read-only and require an updated_utc timestamp no more than 48 hours old.
- Both current on-court team results and current player's verified game rows are limited to dates strictly before today's Eastern calendar day. The V228 coverage ledger must also show an observation timestamp <= forecast creation time.
- Only scheduled/pregame games with two rated verified D1 opponents, valid source timing, at least 30 minutes before start and no more than 42 hours ahead qualify for new forecasts.
- Per (division, ESPN game ID, model ID), only the FIRST eligible pretip forecast is ever stored. Neither new data nor subsequent reruns overwrite it. Final results are stored separately, and no game already tipped can acquire a synthetic first forecast.
- Predictions are graded only when the saved original forecast predates game start. The official comparison uses existing V97 official pretip forecasts for the SAME matchups and shows both paired and all-shadow sample sizes.
- The model's first forecast archive exists entirely under data/shadow_multifactor_v260/2026-27. It never writes to data/ratings, data/predictions or data/prospective/2026-27.
- Missing talent, minutes, coach or roster records are marked unavailable. They do not imply a player, coach or roster has low talent.
- The model explicitly excludes incomplete-history D1 newcomers under the V227 rule.

## Files and workflows

- shadow_multifactor_v260.py — research rating/forecast engine, independently timestamped first forecasts, result grading, coverage and same-game official comparisons.
- shadow_coaches_v260.py — ESPN season-specific head-coach identity evidence with strict role and team verification.
- test_shadow_multifactor_v260.py — deterministic input, chronology, coach-role, player-minute coverage and immutable forecast tests.
- .github/workflows/shadow_multifactor_v260.yml — independent schedule and test workflow.
- data/shadow_multifactor_v260/2026-27/first_forecasts.csv — never rewrite an existing forecast.
- data/shadow_multifactor_v260/2026-27/results.csv — separately recorded actual results.
- data/shadow_multifactor_v260/2026-27/mens_latest_components.csv and womens_latest_components.csv — overwritten CURRENT feature snapshots, explicitly not historical saved ratings.
- data/shadow_multifactor_v260/2026-27/summary.json — source digests, coverage, limitations and paired results.

The workflow is scheduled three times per day on main, following the morning official rating refresh and afternoon player box-score collection. On pull requests, run regression tests only; there are no committed shadow first forecasts before merging. After merging, it can also be started manually.

## Scientific and engineering next steps

1. Improve and independently verify coaching attribution. An API's team-association alone is not proof of head-coach role and cannot support a coaching-quality rating.
2. Source licensed recruiting / transfer rankings with independently verifiable dates, for both divisions.
3. Add opponent-adjusted player possession/lineup value only after identity, play-by-play coverage and game availability are confirmed.
4. Evaluate fixed candidates using historical time-ordered validation followed by prospectively locked matches. Never tune coefficients on the games they are evaluated against.
5. At the January 1, 2027 checkpoint, compare the shadow and official on identical first-forecast games, with MAE, winner accuracy, signed bias, and informative disagreements.

**No changes to production ratings, probability models, the website, official forecast archives, or the existing evaluation plan.**

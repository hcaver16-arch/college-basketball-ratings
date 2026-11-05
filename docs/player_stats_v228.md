# Courtside V228 · Verified 2026–27 Player Statistics

The Players page and Home Player Leaders tile use a separate saved archive of ESPN individual game box scores. They are not derived from historical rosters, guessed projections, or team scoring averages.

## Initial collection

After merging, manually run Actions → Collect verified player box scores V228 → Run workflow on main. It will run automatically at 14:40 UTC daily thereafter. The first run fetches D1 scoreboard dates beginning November 1, 2026, and all available finalized games. Later runs recheck the four most recent days, fill downtime gaps from the last successful discovery date, and retry previously missing team box scores. Large missed runs can take longer.

## Eligibility and coverage

- ESPN's group-50 team directory defines which team box scores count as D1. A D1 team playing a non-D1 opponent is eligible; the non-D1 opponent's player rows are not imported.
- A verified team box score has player IDs, names, nonnegative numeric minutes/points/rebounds/assists and reconciles player points with ESPN's final team score to within two (technical foul exception). Unparseable or missing box scores are recorded in an audit, not replaced with zeros.
- The UI publishes national-style leaderboards only after 30 ESPN-discovered completed D1 team-game box scores, 95% observed parsing coverage, and a report refreshed within 60 hours. This is a deliberately strict, provisional threshold, not a complete independent inventory of all NCAA games.
- Player GP is the number of archived verified box scores in which the player actually appeared. Per-game averages are total points/rebounds/assists/minutes divided by observed GP; absences and unobserved games are never fabricated. Search, team filter, rankings by PPG/RPG/APG/MPG, minimum GP, and individual game log are provided.
- ESPN response structure can change. Complete team-game archives are append-only, and incomplete team games remain retriable. A scoreboard discovery failure fails visibly before updating that division's discovery watermark. Processing uses at most eight concurrent summary requests.
- The leaderboard is provisional, particularly for players with one or two appearances. Coaches may use different GP qualification rules. The page includes filters for minimum observed games and a coverage disclaimer.
- Daily updates can be delayed by ESPN's game finalization or GitHub Actions scheduling. Header dates and audit diagnostics identify data freshness.

## Files

Under data/player_stats_v228/2026-27/:
- <sport>_games.csv.gz: verified athlete-per-game rows, with ESPN game IDs
- <sport>_coverage.csv: ESPN-discovered D1 team-game box-score success/failure audits
- <sport>_players.csv.gz: per-player totals and observed per-game rates
- <sport>_summary.json: fresh coverage and publication readiness per division
- summary.json: combined men/women collection status

Not modified: official rating engine, saved ratings, prospective forecast journals, team roster research, SOS/SOR, or tournament projections.

## Follow-up quality checks

After the first run, review per-division verified / discovered ratios, reasons for unverified games, player counts, and unusually high per-game values. Compare a sample of ESPN box scores by hand. If parsing coverage falls below threshold, the national leaderboard and Home tile are automatically withheld, while saved evidence remains available for diagnosis.

## V231 — What to do when ESPN's athlete point totals disagree with the final score

A live-source inspection on November 5, 2026 found nine women's team-game boxes where ESPN's *raw individual-athlete PTS column* summed to fewer points than ESPN's own final team score (shortfalls ranged from 3 to 12 points). In all nine cases the original V228 parser exactly matched the raw ESPN individual-point total. All athletes omitted by the parser were explicitly marked didNotPlay and had no points; there was no evidence of omitted positive-point athlete rows.

The V231 collector update **does not change accepted player statistics or loosen the score check**. It only labels two separate failure classes in the saved coverage CSV and per-division summary:

- `ESPN source mismatch:` means all valid raw ESPN player points were parsed, but those numbers still disagree with ESPN's reported final; no legitimate points can safely be assigned to an individual player.
- `Possible parser omission:` means ESPN's raw point rows contain more points than the parser obtained; this should trigger a code-level review rather than being blamed on ESPN's source.

Both remain unverified, continue daily retries, and are excluded from the player leaderboards. The divisional summary exposes `espn_source_score_mismatch_boxscores` and `possible_parser_scoring_gap_boxscores` counts after the next successful V228 collection. The collectors never fabricate missing scoring attribution. Review the V231 diagnostic workflow logs for source examples; note that ESPN's unofficial API might eventually correct the player box scores without the site changing code.

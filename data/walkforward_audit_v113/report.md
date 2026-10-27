# Courtside V113 — Historical walk-forward audit

**READ-ONLY on research inputs. No ratings, forecasts, site, or model files changed.**

## Inventory overview

- Files scanned: **77**
- Files with both timestamp fields: **2**
- Rows with parsed as-of before tipoff: **0**
- Rows with as-of at or after tipoff: **0**
- Unverifiable date comparisons: **0**

## Archive types

| Inferred category | Files |
|---|---:|
| forecast_or_model_snapshot | 2 |
| game_results_or_schedule | 5 |
| ratings_or_priors | 47 |
| roster_or_player | 23 |

## V105 locations found

- `data/roster_experiment_v105/mens-college-basketball_experimental_roster_sensitivity.csv`
- `data/roster_experiment_v105/summary.json`
- `data/roster_experiment_v105/womens-college-basketball_experimental_roster_sensitivity.csv`

## CSV files with timestamp evidence

| File | Rows | Pregame | After/at tipoff | Unverifiable |
|---|---:|---:|---:|---:|
| `data/prospective/2026-27/forecasts.csv` | 0 | 0 | 0 | 0 |
| `data/prospective/2026-27/roster_pairs_v109.csv` | 0 | 0 | 0 | 0 |

## Missing known prospective archives

- All three known V97/V109 CSV files are present

## Decision

**Historical hyperparameter tuning is NOT authorized by this audit.**

- No verified historical input-availability timestamps or replayable per-game as-of ratings established by file inventory alone
- Competition venue requires source verification: populated Neutral values are not proof they are accurate
- Roster snapshots must be specific to the season and collected before each forecast, not just labeled with a season
- Separate chronological train/validation/test partitions and identical-game evaluation remain to be implemented

## Next actions

1. Inspect `inventory.json` for historical game tables and exact season fields.
2. Identify raw event timestamps plus archival acquisition timestamps for every required rating feature.
3. Establish a validated source for home/away/neutral site flags.
4. Rebuild past ratings progressively from games completed strictly before each scheduled tipoff.
5. Only then evaluate frozen model variants on held-out periods and identical matchups.

**Scope:** JSON and Parquet contents are not parsed; the inventory alone cannot prove leakage-free replay.

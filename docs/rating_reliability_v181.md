# V181 — Rating-engine reliability

This patch fixes an observed type-sensitivity bug by normalizing Home ID and Away ID to trimmed strings **before** calculating rating indices. It rejects missing, placeholder, or equal IDs.

The engine now accepts only explicit `Home` and `Neutral` venues when fitting ratings. Unknown, missing, or other venue types are excluded from the fit and counted in the returned `unknown_venue_games` metadata. This avoids incorrectly assigning 3 points of home advantage to an unverified venue. When a feed consistently uses `Away` or alternative labels, those games will be excluded until provenance is established. Both ESPN ingestion paths currently emit `Home` and `Neutral`.

Preserved: 3-point home advantage on Home games, zero on Neutral, ridge 8, 40-point margin cap, minimum 20 games, preseason blending coefficients, win probability, prediction archives.

Run `python test_rating_reliability_v181.py` and `python validate_model_v180.py` for synthetic checks. This is not a predictive-accuracy improvement claim. Excluded venues may decrease game count, and the diagnostic is available for reporting; no existing forecasts are edited.

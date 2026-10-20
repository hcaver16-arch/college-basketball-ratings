# College Basketball Ratings — starter website

This is an initial **working prototype**, not a finished automatic sports data service. Sample teams, sample schedules, and ratings are **invented for demonstration**. It supports independently switching men's and women's leagues, calculating predicted spreads from user-supplied ratings, simple SOS rankings, and evaluating final scores. It does not currently import data automatically or calculate team ratings from results; those are the next integration steps.

## Publish for free (no coding experience needed)
1. Create free accounts at https://github.com and https://share.streamlit.io.
2. In GitHub, create a new repository, such as `basketball-ratings`.
3. Upload `app.py` and `requirements.txt` into the repository root (not inside a folder).
4. In Streamlit Community Cloud, choose **Create app** / **Deploy an app**, connect your GitHub repository, set entrypoint to `app.py`, and deploy.
5. The website uses a free `.streamlit.app` address; no paid domain is needed.

## Real data CSV format
Teams CSV (one row per team):
```
league,team,rating
M,Example University,10.5
W,Example University,12.0
```
Games CSV (one row per game; scores can be blank for future games):
```
league,date,home_team,away_team,venue,home_score,away_score
M,2026-11-09,Example University,Another University,home,,
```
`venue`: `neutral` or `home`. For games marked `home`, `home_team` is assumed to host. All school names must match the team CSV exactly.

## Rating and spread
An uploaded `rating` is interpreted as projected neutral-court scoring margin versus an average Division I opponent, in **points per game**. For this starter, projected home margin = home rating - away rating + HCA (or 0 at a neutral venue). This is a baseline; it is not yet opponent-adjusted, tempo-adjusted, or calibrated against historical results.

## Next development steps
- Connect a permitted game and box-score provider for both leagues; validate full Division I coverage and rate limits.
- Add an adjusted efficiency-based ratings model, preseason priors, and weekly snapshots.
- Add pace-based score totals, location-aware SOS/expected wins, and uncertainty calibration.
- Set up automatic weekly data ingestion with a scheduled workflow and status/error reporting.
- Keep women’s and men’s data isolated so either one can be hidden/removed later.

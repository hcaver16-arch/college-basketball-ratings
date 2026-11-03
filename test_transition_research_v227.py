"""V227: source-confirmed newcomer, research-only estimates and immutable forecasts."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import ast
import csv
import json
import pandas as pd
from transition_research_v227 import (
    KNOWN_TRANSITIONS, MIN_OPPONENT_GAMES, MIN_DISTINCT_D1_OPPONENTS,
    transitioning_ids, ncaa_postseason_ineligible, newcomer_game,
    opponent_adjusted_research, research_report,
)

assert KNOWN_TRANSITIONS["2697"]["name"] == "West Florida Argonauts"
assert KNOWN_TRANSITIONS["2697"]["source"].startswith("https://news.uwf.edu/")
assert transitioning_ids("2026-27") == {"2697"}
assert "2697" in ncaa_postseason_ineligible("2026-27")
assert "2697" in ncaa_postseason_ineligible("2028-29")
assert "2697" not in ncaa_postseason_ineligible("2029-30")
assert not transitioning_ids("2025-26")

d1 = {"2697", "200", "201", "202", "203"}
assert newcomer_game({"Home ID": "200", "Away ID": "2697"}, d1)
assert newcomer_game({"home_id": "2697", "away_id": "200"}, d1)
assert not newcomer_game({"Home ID": "200", "Away ID": "201"}, d1)
assert not newcomer_game({"Home ID": "2697", "Away ID": "999"}, d1)
assert not newcomer_game({"Home ID": "200", "Away ID": "2697"}, d1, season="2025-26")

games = []
for i, opp in enumerate(("200", "201", "202", "200", "203"), 1):
    games.append({
        "Game ID": str(i), "Date": "2026-11-02", "Status": "Final",
        "Home ID": "2697" if i % 2 else opp, "Away ID": opp if i % 2 else "2697",
        "Home score": 68 if i % 2 else 61, "Away score": 65 if i % 2 else 64,
        "Venue": "Neutral" if i == 2 else "Home",
    })
priors = {"200": 7.0, "201": 10.0, "202": -1.0, "203": 4.0}
eligible = opponent_adjusted_research("2697", pd.DataFrame(games), d1, priors, date(2026,11,3))
assert eligible["eligible_games"] == 5
assert eligible["distinct_opponents"] == 4
assert eligible["research_estimate"] is not None
assert eligible["status"] == "RESEARCH_ONLY_UNVALIDATED"

# Fewer than 5 completed against three different rated verified D1 opponents:
# absolutely no research estimate and no official rating.
for subset in (games[:1], games[:4], [games[0]] * 5):
    partial = opponent_adjusted_research("2697", pd.DataFrame(subset), d1, priors, date(2026,11,3))
    assert partial["research_estimate"] is None
    assert partial["status"] == "INSUFFICIENT_COMPLETED_D1_GAMES"
assert opponent_adjusted_research("2697", pd.DataFrame(), d1, priors, date(2026,11,3))["research_estimate"] is None
assert opponent_adjusted_research("2697", pd.DataFrame(games), d1, priors, date(2026,11,1))["eligible_games"] == 0
assert opponent_adjusted_research("2697", pd.DataFrame(games), d1, priors, date(2026,11,3))["research_estimate"] != 0.0

# Exclude non-D1 opponents, future dates, duplicates, invalid venues/scores.
poisoned = pd.DataFrame(games + [
    {**games[0], "Home score": 500},
    {**games[1], "Game ID": "non-d1", "Away ID": "999"},
    {**games[2], "Game ID": "future", "Date": "2026-11-08"},
    {**games[3], "Game ID": "bad-venue", "Venue": "Unknown"},
    {**games[4], "Game ID": "bad-score", "Home score": -1},
])
clean = opponent_adjusted_research("2697", poisoned, d1, priors, date(2026,11,3))
assert clean["eligible_games"] == 5, clean
assert clean["research_estimate"] == eligible["research_estimate"]

# Recreate archived inputs without any GitHub/network dependence.
with TemporaryDirectory() as tmp:
    root = Path(tmp)
    for sport in ("mens-college-basketball", "womens-college-basketball"):
        target = root / "data" / "ratings" / sport
        target.mkdir(parents=True)
        frame = pd.DataFrame([
            {"Team ID":tid, "Team": "A", "Current power":power,
             "Preseason rating": power, "Games played":1}
            for tid,power in priors.items()
        ])
        frame.to_csv(target / "latest.csv.gz", index=False, compression="gzip")
        pd.DataFrame(games).to_csv(target/"season_2026-27.csv.gz",index=False,compression="gzip")
        evidence = root / "data" / "d1_repair_v108"
        evidence.mkdir(parents=True,exist_ok=True)
        pd.DataFrame([{"team_id":"2697","team":"West Florida Argonauts",
                       "membership_status":"reclassifying_d1_basketball",
                       "unavailable_rating":True}]).to_csv(
            evidence/f"{sport}_membership_evidence.csv",index=False
        )
        rows, summary = research_report(root, sport, d1 | {"999"}, date(2026,11,3))
        west = rows.set_index("team_id").loc["2697"]
        assert bool(west["source_confirmed_transition"])
        assert west["research_estimate"] == eligible["research_estimate"]
        assert bool(west["ncaa_postseason_eligible"]) is False
        assert west["release_status"] == "MANUAL_HOLD_PENDING_VALIDATION"
        assert bool(west["official_forecast_eligible"]) is False
        assert summary["missing_official_d1_ratings"] == 2
        assert summary["source_confirmed_transition_count"] == 1
        unknown = rows.set_index("team_id").loc["999"]
        assert unknown["release_status"] == "REQUIRES_MEMBERSHIP_REVIEW"
        # An in-season low-information rating must not silently release the newcomer.
        frame.loc[len(frame)] = ["2697","West Florida Argonauts",-0.12,0,1]
        frame.to_csv(target/"latest.csv.gz",index=False,compression="gzip")
        rows2,summary2 = research_report(root,sport,d1,date(2026,11,3))
        west2 = rows2.set_index("team_id").loc["2697"]
        assert bool(west2["in_current_saved_ratings"])
        assert west2["release_status"] == "MANUAL_HOLD_PENDING_VALIDATION"
        assert summary2["missing_official_d1_ratings"] == 0

# Official first-forecast system must refuse newcomer matchups even if one
# game's margin could produce a misleading "official" neutral-prior rating.
import prospective_archive_v97 as v97
now=datetime(2026,11,3,16,tzinfo=timezone.utc)
future=(now+timedelta(hours=10)).isoformat()
games_map = {
    "west":{"game_id":"west","game_start_utc":future,"final":False,
            "home_id":"200","away_id":"2697", "neutral":False,"game_date_et":"2026-11-03",
            "home_team":"Home", "away_team":"West Florida"},
    "regular":{"game_id":"regular","game_start_utc":future,"final":False,
            "home_id":"200","away_id":"201","neutral":False,"game_date_et":"2026-11-03",
            "home_team":"Home", "away_team":"Away"},
}
models=[{"id":"official_saved_v97","asof":now-timedelta(hours=1),
         "ratings":{"200":7.0,"201":10.0,"2697":-0.48},
         "file":"test.csv.gz","sha256":"sample","type":"official_saved_model"}]
new = v97.new_forecasts(games_map,models,[],now,"2026-27","mens",30)
assert [x["game_id"] for x in new]==["regular"], new
assert v97.new_forecasts(games_map,models,new,now,"2026-27","mens",30)==[]
# A legacy locked record is immutable; no rewritten or retroactive first guess.
legacy=[{**new[0],"game_id":"west","predicted_home_margin":5.2}]
assert not any(x["game_id"]=="west" for x in v97.new_forecasts(
    games_map,models,legacy,now,"2026-27","mens",30
))

# Source and tournament safeguards are separate from model math.
for path in ("app.py","rating_engine.py","prediction_archive.py","bracketology_v138.py",
             "transition_research_v227.py"):
    ast.parse(Path(path).read_text(),filename=path)
assert "newcomer_game(row, verified_d1)" in Path("app.py").read_text()
assert '"New D1 program · rating not validated"' in Path("app.py").read_text()
assert "if newcomer_game(g):continue" in Path("prediction_archive.py").read_text()
assert "ncaa_postseason_ineligible(" in Path("bracketology_v138.py").read_text()
assert 'data=data[~data["Team ID"].isin(ncaa_postseason_ineligible("2026-27"))]' in Path("bracketology_v138.py").read_text()
assert "git add -- data/transition_research_v227/" in Path(".github/workflows/audit_transition_research_v227.yml").read_text()
assert "make_combined(" in Path("rating_engine.py").read_text()
print("V227 source-verified transitions, research-only estimates and immutable forecast holds passed")

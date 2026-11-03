"""V228: live-season player boxscore collection is verifiable, resumable and isolated."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import ast
import json
import pandas as pd

import player_stats_v228 as collect
import player_stats_ui_v228 as ui
from player_stats_import import parse_boxscore, games_from_schedule

NOW = datetime(2026, 11, 3, 15, tzinfo=timezone.utc)
SPORT = "mens-college-basketball"
d1 = {str(i) for i in range(200, 402)}
assert len(d1) >= 200
assert collect.DIR == Path("data/player_stats_v228/2026-27")

# Real ESPN boxscore parser contract: original athlete IDs and played-only rows.
def team_group(team_id, points, player_id):
    return {"team": {"id": team_id}, "statistics": [{
        "labels": ["MIN", "PTS", "REB", "AST"],
        "athletes": [
            {"athlete": {"id": player_id, "displayName": "Player "+team_id},
             "stats": ["28:30", str(points), "4", "3"]},
            {"athlete": {"id": "DNP-"+team_id, "displayName": "Bench"},
             "didNotPlay": True, "stats": ["--","--","--","--"]},
        ],
    }]}

sample = {"boxscore": {"players": [team_group("200", 27, "p200"),
                                   team_group("201", 21, "p201")]}}
parsed = parse_boxscore(sample, "200", "g1")
assert len(parsed) == 1 and parsed[0]["Player ID"] == "p200"
assert parsed[0]["Points"] == 27
assert parsed[0]["Minutes"] == 28.5
assert parsed[0]["Assists"] == 3
assert "DNP-200" not in [r["Player ID"] for r in parsed]
assert collect._valid_player_rows(parsed, 27)[0]
assert not collect._valid_player_rows(parsed, 10)[0]
assert collect._valid_player_rows(parsed, float("nan"))[0]
assert not collect._valid_player_rows([{**parsed[0], "Rebounds": -1}], 27)[0]
assert not collect._valid_player_rows([parsed[0], parsed[0]], 54)[0]

assert games_from_schedule({"events":[{"id":"g1","status":{"type":{"completed":True}}},
                                           {"id":"g2","status":{"type":{"completed":False}}}]})==["g1"]

games = {
    str(i): {
        "game_id":str(i), "game_start_utc": (NOW-timedelta(days=1)).isoformat(),
        "game_date_et": "2026-11-02", "final": True,
        "home_id": "200", "away_id":"201", "home_team":"Home College",
        "away_team":"Away College","home_score":27,"away_score":21,
    } for i in range(1, 17)
}

def fake_day(sport, day, session=None):
    return games
def fake_box(sport, gid, session=None):
    if gid in failed_games:
        return {"boxscore":{"players":[team_group("200",27,"p200")]}}
    return sample

with TemporaryDirectory() as tmp:
    root = Path(tmp)
    failed_games = {"1", "2"}
    with patch.object(collect, "_fetch_day", side_effect=fake_day), patch.object(
        collect, "_fetch_box", side_effect=fake_box
    ):
        report = collect._run_division(SPORT, root, NOW, d1_ids=d1)
    assert report["discovered_d1_team_game_boxscores"] == 32, report
    assert report["verified_d1_team_game_boxscores"] == 30, report
    assert report["unverified_d1_team_game_boxscores"] == 2, report
    assert not report["player_leaders_publishable"]
    assert abs(report["observed_boxscore_coverage"] - 0.9375) < 1e-5
    assert report["athletes_with_observed_games"] == 2
    audit_path = root / collect.DIR / f"{SPORT}_coverage.csv"
    player_path = root / collect.DIR / f"{SPORT}_players.csv.gz"
    line_path = root / collect.DIR / f"{SPORT}_games.csv.gz"
    assert audit_path.exists() and player_path.exists() and line_path.exists()
    lines = pd.read_csv(line_path)
    assert len(lines) == 30
    assert set(lines["Source"].str.contains("ESPN individual box score")) == {True}
    summary = json.loads((root/collect.DIR/f"{SPORT}_summary.json").read_text())
    assert summary["last_discovered_date_et"] == "2026-11-03"
    assert summary["publication_minimum_coverage"] == 0.95

    # Incomplete coverage must not show plausible-looking "national leaders".
    rows, message, _, ready = ui.home_leader_rows(
        "Men's", {"200", "201"}, root=root, now=NOW
    )
    assert not rows and not ready and "collecting" in message
    assert not ui.available(summary, now=NOW)

    # The next collection retries only the two incomplete team-game records.
    failed_games = set()
    calls = []
    def counting_box(sport, gid, session=None):
        calls.append(gid)
        return fake_box(sport, gid, session)
    with patch.object(collect, "_fetch_day", side_effect=fake_day), patch.object(
        collect, "_fetch_box", side_effect=counting_box
    ):
        updated = collect._run_division(
            SPORT, root, NOW+timedelta(hours=2), d1_ids=d1
        )
    assert sorted(calls) == ["1","2"], calls
    assert updated["verified_d1_team_game_boxscores"] == 32
    assert updated["player_leaders_publishable"]
    assert updated["observed_boxscore_coverage"] == 1.0
    athlete_rows = pd.read_csv(player_path, dtype={"Player ID": str})
    assert len(athlete_rows) == 2
    assert athlete_rows["GP"].tolist() == [16, 16]
    assert set(athlete_rows["PPG"]) == {21.0,27.0}
    assert set(athlete_rows["RPG"]) == {4.0}
    assert set(athlete_rows["APG"]) == {3.0}
    assert len(pd.read_csv(line_path)) == 32
    assert len(pd.read_csv(audit_path)) == 32

    # A third run never silently changes a verified historical player game.
    def should_not_refetch(*args, **kwargs):
        raise AssertionError("Verified boxscore was fetched again")
    with patch.object(collect, "_fetch_day", side_effect=fake_day), patch.object(
        collect, "_fetch_box", side_effect=should_not_refetch
    ):
        again = collect._run_division(
            SPORT, root, NOW+timedelta(hours=4), d1_ids=d1
        )
    assert again["summary_games_fetched"] == 0
    assert len(pd.read_csv(line_path)) == 32
    assert ui.available(again, NOW+timedelta(hours=4))
    assert not ui.available(again, NOW+timedelta(days=4))

    leaderboard = ui.ranked_players(athlete_rows, "PPG", min_games=5, team_ids={"200","201"})
    assert len(leaderboard)==2 and leaderboard.iloc[0]["Player ID"]=="p200"
    assert ui.ranked_players(athlete_rows,"PPG",17).empty
    assert ui.ranked_players(athlete_rows,"bad",1).empty
    assert len(ui.ranked_players(athlete_rows,"PPG",1,team_ids={"200"}))==1
    home_rows, msg, note, ready = ui.home_leader_rows(
        "Men's", {"200", "201"}, root=root, now=NOW+timedelta(hours=4)
    )
    assert ready and len(home_rows)==3, home_rows
    assert home_rows[0][0].startswith("Points") and home_rows[0][1]=="27.0"
    assert "100%" in note
    missing_rows, _, _, valid = ui.home_leader_rows(
        "Women's", {"200"}, root=root, now=NOW
    )
    assert not missing_rows and not valid

    # A failed scoreboard day cannot corrupt data, nor mark a failed scan as
    # fully discovered. Archives and their prior date watermark remain intact.
    before = (root/collect.DIR/f"{SPORT}_summary.json").read_text()
    def broken_day(*args, **kwargs):
        raise RuntimeError("ESPN unavailable")
    with patch.object(collect, "_fetch_day", side_effect=broken_day):
        try:
            collect._run_division(SPORT, root, NOW+timedelta(days=1), d1_ids=d1)
            raise AssertionError("Expected schedule failure")
        except RuntimeError as exc:
            assert "scoreboard discovery failed" in str(exc)
    assert (root/collect.DIR/f"{SPORT}_summary.json").read_text() == before

# Structural regressions: no model edits, new page and read-only home tile.
app = Path("app.py").read_text()
insights = Path("home_insights_v219.py").read_text()
for path in ["player_stats_v228.py", "player_stats_ui_v228.py", "app.py",
             "home_insights_v219.py", "player_stats_import.py"]:
    ast.parse(Path(path).read_text(), filename=path)
assert 'sections=["Home","Games","Rankings","Players",' in app
assert 'more_pages = ["Players", "Teams",' in app
assert 'if selected_section == "Players":' in app
assert 'render_players(league, saved_player_ratings)' in app
assert 'st.stop()' in app
assert '"Players", "2026–27" if player_ready else "Collecting"' in insights
assert '"Players"' in insights
assert 'player_rows=player_rows' in insights
assert "home_leader_rows(league, ids)" in insights
workflow = Path(".github/workflows/collect_player_stats_v228.yml").read_text()
assert "git add -- data/player_stats_v228/2026-27/" in workflow
assert "python player_stats_v228.py" in workflow
assert "data/ratings/" not in workflow and "data/prospective/" not in workflow
print("V228 verified player archive, stale/missing safeguards, home tile and navigation validated")

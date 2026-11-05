"""V231: distinguish upstream ESPN source discrepancies from scorer parsing bugs."""
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import pandas as pd

from player_stats_import import parse_boxscore, audit_team_scoring_source
from player_stats_v228 import _run_division, DIR

NOW = datetime(2026, 11, 5, 16, tzinfo=timezone.utc)
SPORT = "womens-college-basketball"
D1 = {str(i) for i in range(200, 450)}
START = "2026-11-04T20:00:00+00:00"

def group(tid, points, extra=None):
    return {"team":{"id":tid}, "statistics":[{
        "labels":["MIN","PTS","FG","3PT","FT","REB","AST"],
        "athletes":[
            {"athlete":{"id":f"{tid}-first","displayName":f"Player {tid}"},
             "stats":["30:00",str(points),"7-15","1-3","5-6","5","2"]},
            *([extra] if extra else []),
            {"athlete":{"id":f"{tid}-inactive","displayName":"Inactive player"},
             "didNotPlay":True,"stats":[]},
        ],
    }]}
def doc(home_score=70, extra=None):
    return {"boxscore":{"players":[group("200",70,extra),group("201",21)]}}
def discover(_sport, _day, session=None):
    return {"g1":{"game_id":"g1","game_date_et":"2026-11-04",
                  "game_start_utc":START,"final":True,"home_id":"200",
                  "away_id":"201","home_team":"Home","away_team":"Away",
                  "home_score":76,"away_score":21}}
def collect(root, payload):
    with patch("player_stats_v228._fetch_day",side_effect=discover),patch(
        "player_stats_v228._fetch_box",return_value=payload
    ):
        return _run_division(SPORT,root,NOW,d1_ids=D1)

# Original ESPN has 70 raw player PTS even though the team final reports 76.
original=doc()
played=parse_boxscore(original,"200","g1")
assert len(played)==1 and played[0]["Points"]==70
audit=audit_team_scoring_source(original,"200","g1",played,76)
assert audit["status"]=="ESPN_RAW_PLAYER_TOTAL_DIFFERS_FROM_TEAM_FINAL"
assert audit["parsed_player_points"]==70
assert audit["raw_espn_player_points"]==70
assert audit["espn_final_team_points"]==76
assert not audit["missing_positive_scoring_athlete_rows"]

with TemporaryDirectory() as tmp:
    root=Path(tmp)
    one=collect(root,original)
    assert one["discovered_d1_team_game_boxscores"]==2
    assert one["verified_d1_team_game_boxscores"]==1
    assert one["unverified_d1_team_game_boxscores"]==1
    assert one["espn_source_score_mismatch_boxscores"]==1
    assert one["possible_parser_scoring_gap_boxscores"]==0
    coverage=root/DIR/f"{SPORT}_coverage.csv"
    games=root/DIR/f"{SPORT}_games.csv.gz"
    row=pd.read_csv(coverage,dtype={"Team ID":str})
    home=row.loc[row["Team ID"].eq("200")].iloc[0]
    assert home["Status"]=="unverified"
    assert "ESPN source mismatch:" in home["Reason"],home
    assert "no omitted scoring rows" in home["Reason"]
    # Unverifiable player's 70 points must not contaminate official player GPA.
    archived=pd.read_csv(games,dtype={"Team ID":str})
    assert set(archived["Team ID"])=={"201"}

    # Cases where positive scoring raw rows were excluded must be flagged
    # differently and never silently blessed as an upstream ESPN error.
    missed={"athlete":{"id":"200-extra","displayName":"Second scorer"},
            "stats":["--","4","1-1","0-0","2-2","3","1"]}
    missing=doc(extra=missed)
    parsed=parse_boxscore(missing,"200","g1")
    assert len(parsed)==1
    problem=audit_team_scoring_source(missing,"200","g1",parsed,76)
    assert problem["status"]=="PARSER_OR_ATHLETE_ROW_GAP"
    assert problem["raw_espn_player_points"]==74
    assert problem["parsed_player_points"]==70
    assert len(problem["missing_positive_scoring_athlete_rows"])==1
    two=collect(root,missing)
    assert two["espn_source_score_mismatch_boxscores"]==0
    assert two["possible_parser_scoring_gap_boxscores"]==1
    row=pd.read_csv(coverage,dtype={"Team ID":str})
    home=row.loc[row["Team ID"].eq("200")].iloc[0]
    assert home["Status"]=="unverified"
    assert "Possible parser omission:" in home["Reason"]
    assert len(pd.read_csv(games))==1

    # A corrected ESPN player feed can eventually verify the score without
    # retroactively updating already-verified opponent statistics.
    corrected=doc(extra={
        "athlete":{"id":"200-extra","displayName":"Second scorer"},
        "stats":["15:00","6","2-2","0-0","2-2","3","1"],
    })
    three=collect(root,corrected)
    assert three["verified_d1_team_game_boxscores"]==2
    assert three["unverified_d1_team_game_boxscores"]==0
    assert three["espn_source_score_mismatch_boxscores"]==0
    assert three["possible_parser_scoring_gap_boxscores"]==0
    assert set(pd.read_csv(games,dtype={"Team ID":str})["Team ID"])=={"200","201"}

print("V231 ESPN upstream mismatch/parser omission evidence, retry and safe archive tests passed")

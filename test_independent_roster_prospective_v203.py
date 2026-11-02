"""V203 prospective roster experiment tests: historical locks and source chronology."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import json
import pandas as pd

from independent_roster_prospective_v203 import (
    candidates,load_evidence,lock_pairs,run,MODEL_ID
)
from prospective_roster_eval_v109 import FIELDS,rows
from prospective_archive_v97 import FIELDS as BASE_FIELDS, RESULT_FIELDS
UTC=timezone.utc
def dt(v):return datetime.fromisoformat(v.replace("Z","+00:00"))
ASOF="2026-11-02T20:40:48Z"
NOW=dt("2026-11-03T14:00:00Z")

def setup_root(root):
    root=Path(root)
    folder=root/"data"/"official_roster_evidence_v202"
    folder.mkdir(parents=True)
    folder.joinpath("summary.json").write_text(json.dumps({
        "checked_utc":ASOF,"division":"mens-college-basketball","model_changed":False
    }))
    previous=[];current=[];stats=[]
    for tid in ("2638","94","105"):
        for n in range(1,9):
            pid=tid+"-"+str(n)
            previous.append({"Team ID":tid,"ESPN Player ID":pid,
                "Matched ESPN prior box scores":True,"Matched ESPN current roster":False,
                "Official source URL":"https://school.edu/2025-26","Source checked UTC":"2026-11-02",
                "Evidence classification":"Official + ESPN prior box scores"})
            current.append({"Team ID":tid,"ESPN Player ID":pid,
                "Matched ESPN prior box scores":True,"Matched ESPN current roster":True,
                "Official source URL":"https://school.edu/2026-27","Source checked UTC":"2026-11-02",
                "Evidence classification":"Official + ESPN current roster"})
            stats.append({"Team ID":tid,"Player ID":pid,"Minutes":100*n,"Source":"ESPN season 2026",
                "Game IDs":"401test","Games with box score":1})
    # Only UTEP and NKU usable. Third team has 7/8 verified stats and should fail.
    stats=[row for row in stats if row["Player ID"]!="105-8"]
    # Make UTEP returning retention 0%: all 2026-27 players are new IDs.
    for row in current:
        if row["Team ID"]=="2638":
            row["ESPN Player ID"] = "new-"+row["ESPN Player ID"]
    pd.DataFrame(previous).to_csv(folder/"linked_players.csv",index=False)
    pd.DataFrame(current).to_csv(folder/"linked_current_players.csv",index=False)
    pd.DataFrame(stats).to_csv(root/"data/mens-college-basketball_previous_stats.csv.gz",
                                index=False,compression="gzip")
    directory=root/"data"/"prospective"/"2026-27"
    directory.mkdir(parents=True)
    return directory

def baseline(game_id,home,away,start="2026-11-03T16:00:00Z",
             created="2026-11-03T13:40:00Z",model="official_saved_v97"):
    return {
        "season":"2026-27","division":"mens","game_id":game_id,
        "game_start_utc":start,"home_id":home,"away_id":away,
        "home_team":"Home","away_team":"Away","neutral":"true",
        "model_id":model,"forecast_created_utc":created,
        "ratings_snapshot_utc":"2026-11-03T13:30:00Z",
        "snapshot_file":"data/ratings/mens-college-basketball/latest.csv.gz",
        "snapshot_sha256":"savedsha","home_rating":"10","away_rating":"8",
        "predicted_home_margin":"2","forecast_type":"official_saved_model"
    }

def csvwrite(path,data,columns):
    with path.open("w",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=columns)
        writer.writeheader();writer.writerows(data)

with TemporaryDirectory() as tmp:
    folder=setup_root(tmp)
    evidence,error=load_evidence(Path(tmp),NOW)
    assert error is None,error
    adjustments,audit=candidates(evidence)
    assert set(adjustments)=={"2638","94"},(adjustments,audit)
    assert adjustments["2638"]==-2.5,adjustments
    assert "prior_player_stats_below_90pct" in audit["105"]["blocked_reasons"]
    assert audit["2638"]["qualified"] and audit["94"]["qualified"]
    # The old game may not be retroactively scored even if the files exist now.
    old=baseline("before","2638","94",
       start="2026-11-01T18:00:00Z",created="2026-11-01T15:00:00Z")
    new=baseline("future","2638","94")
    incomplete=baseline("one-sided","2638","105")
    rows_in=[old,new,incomplete]
    csvwrite(folder/"forecasts.csv",rows_in,BASE_FIELDS)
    csvwrite(folder/"results.csv",[],RESULT_FIELDS)
    output=run(Path(tmp),NOW)
    assert output["qualified_team_count"]==2
    assert output["new_pairs"]==1 and output["total_pairs"]==1,output
    assert output["skipped"]["one_or_both_teams_lack_verified_evidence"]==1
    saved=rows(folder/"independent_roster_pairs_v203.csv")
    assert len(saved)==1
    row=saved[0]
    assert row["game_id"]=="future" and row["model_id"]==MODEL_ID
    assert float(row["baseline_predicted_home_margin"])==2
    assert float(row["experimental_predicted_home_margin"])==-3.0
    original=folder.joinpath("independent_roster_pairs_v203.csv").read_bytes()
    again=run(Path(tmp),NOW+timedelta(minutes=1))
    assert again["new_pairs"]==0
    assert folder.joinpath("independent_roster_pairs_v203.csv").read_bytes()==original

    # Grade only against an independently saved final result after the game.
    csvwrite(folder/"results.csv",[{
        "season":"2026-27","division":"mens","game_id":"future",
        "game_start_utc":"2026-11-03T16:00:00Z",
        "result_checked_utc":"2026-11-04T12:00:00Z",
        "home_score":"66","away_score":"70","actual_home_margin":"-4","status":"Final"
    }],RESULT_FIELDS)
    evaluated=run(Path(tmp),dt("2026-11-04T14:00:00Z"))
    assert evaluated["new_pairs"]==0
    metrics=evaluated["paired_results"]["mens"]
    assert metrics["paired_completed_games"]==1,metrics
    assert metrics["baseline_margin_mae"]==6.0
    assert metrics["experimental_margin_mae"]==1.0
    assert folder.joinpath("independent_roster_pairs_v203.csv").read_bytes()==original

    # Source verified AFTER baseline forecast must be rejected; don't backfill.
    late=baseline("late","2638","94",
        start="2026-11-03T18:00:00Z",created="2026-11-02T19:00:00Z")
    added,skipped=lock_pairs([late],[],adjustments,evidence,NOW)
    assert not added and skipped["invalid_evidence_or_pregame_timing"]==1
    # Reject baselines created too long before a pairing run.
    stale=baseline("stale","2638","94",created="2026-11-03T12:00:00Z")
    stale["ratings_snapshot_utc"]="2026-11-03T11:50:00Z"
    added,skipped=lock_pairs([stale],[],adjustments,evidence,NOW)
    assert not added and skipped["baseline_prediction_not_fresh_no_backfill"]==1

    # A model must not infer missing player provenance as a zero-value return.
    path=Path(tmp)/"data"/"mens-college-basketball_previous_stats.csv.gz"
    frame=pd.read_csv(path)
    frame.loc[frame["Player ID"]=="94-3","Game IDs"]=""
    frame.to_csv(path,index=False,compression="gzip")
    revised,_=load_evidence(Path(tmp),NOW)
    signals,reasons=candidates(revised)
    assert "94" not in signals
    assert "prior_player_stats_below_90pct" in reasons["94"]["blocked_reasons"]

# V205: readiness counts only future *locked* baselines, and prioritizes
# opposite teams without treating them as qualified research inputs.
from independent_roster_prospective_v203 import matchup_readiness
research_time=dt("2026-11-03T14:00:00Z")
source_time=dt("2026-11-02T20:40:48Z")
one_sided=baseline("one","2638","unqualified")
two_sided=baseline("two","2638","94")
already_past=baseline("past","2638","94",start="2026-11-03T12:00:00Z")
ready=matchup_readiness([one_sided,two_sided,already_past],
                         {"2638":-2.5,"94":2.5},source_time,research_time)
counts=ready["counts"]
assert counts["upcoming_locked_mens_baselines"]==2
assert counts["exactly_one_team_qualified"]==1
assert counts["both_teams_qualified"]==1
assert counts["both_with_contemporaneous_baseline"]==1
assert ready["opponents_to_prioritize"][0]["team_id"]=="unqualified"
before_verified=baseline("old","2638","94",created="2026-11-02T18:00:00Z")
unready=matchup_readiness([before_verified],
                           {"2638":-2.5,"94":2.5},source_time,research_time)
assert unready["counts"]["both_but_first_baseline_predates_verified_evidence"]==1

print("V203 locks, evidence quality, one-sided rejection and result grading passed")

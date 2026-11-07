"""V233: synthetic parallel-anchor research, immutable locks and movement UI checks."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import numpy as np
import pandas as pd
from rating_engine import calculate_power,make_combined
from anchored_snapshot_v233 import MODEL_ID,create_snapshot,write_snapshot
from paired_anchor_eval_v233 import ANCHOR,OFFICIAL,report,scored_pairs
from prospective_archive_v97 import load_optional,new_forecasts,load_official
from rating_movement_v233 import latest_movement,movement_for_team

NOW=datetime(2026,11,7,18,0,tzinfo=timezone.utc)
SPORT="mens-college-basketball"
def games(day,amount):
    return pd.DataFrame([
        {"Game ID":str(100000+i) if day.startswith("2025") else str(200000+i),
         "Date":day,"Home ID":str(201+i%20),"Away ID":str(201+(i+7)%20),
         "Home":f"Home {i%20}","Away":f"Away {(i+7)%20}",
         "Status":"Final","Venue":"Home" if i%2 else "Neutral",
         "Home score":79+i%17,"Away score":63+i%13}
        for i in range(amount)
    ])
with TemporaryDirectory() as tmp:
    root=Path(tmp)
    base=root/"data"/"ratings"/SPORT
    base.mkdir(parents=True)
    old=games("2025-11-15",1010)
    current=games("2026-11-03",35)
    old.to_csv(base/"history_2025-26.csv.gz",index=False,compression="gzip")
    current.to_csv(base/"season_2026-27.csv.gz",index=False,compression="gzip")
    prior,details=calculate_power(old)
    live,_=calculate_power(current)
    published=make_combined(prior,live,{})
    published.to_csv(base/"latest.csv.gz",index=False,compression="gzip")
    # Production status.json timestamps normally contain microseconds.
    official_time=NOW-timedelta(minutes=30,microseconds=123456)
    (base/"status.json").write_text(json.dumps({
        "snapshot_date":"2026-11-07","updated_utc":official_time.isoformat()
    }))
    anchor=create_snapshot(root,SPORT,NOW)
    assert len(anchor)==len(prior)
    assert set(anchor["model_id"])=={MODEL_ID}
    assert anchor["source_current_sha256"].nunique()==1
    path=write_snapshot(root,SPORT,anchor)
    assert path.exists()
    optional,error=load_optional(SPORT,root,NOW)
    assert not error,error
    assert optional["id"]==ANCHOR
    assert optional["type"]=="optional_experimental"
    official,err=load_official(SPORT,root,NOW)
    assert not err
    assert official["id"]==OFFICIAL
    home,away=prior.iloc[0]["Team ID"],prior.iloc[1]["Team ID"]
    kickoff=NOW+timedelta(hours=7)
    from prospective_archive_v97 import iso
    g={"g1":{"game_id":"g1","game_start_utc":iso(kickoff),
             "game_date_et":"2026-11-07","home_id":str(home),
             "away_id":str(away),"home_team":"Home","away_team":"Away",
             "neutral":False,"final":False}}
    predicted=new_forecasts(g,[official,optional],[],NOW,"2026-27","mens",30)
    assert len(predicted)==2,predicted
    assert len({x["model_id"] for x in predicted})==2
    assert all(x["forecast_created_utc"]<x["game_start_utc"] for x in predicted)
    assert len(new_forecasts(g,[official,optional],predicted,NOW,"2026-27","mens",30))==0
    results=[{"division":"mens","game_id":"g1","status":"Final","actual_home_margin":12.0}]
    pairs,stat=report(predicted,results)
    assert len(pairs)==1 and pairs.iloc[0]["official_margin"]==predicted[0]["predicted_home_margin"]
    assert stat["divisions"]["mens"]["paired_graded_games"]==1
    assert stat["divisions"]["womens"]["paired_graded_games"]==0
    # Never backfill experimental predictions for past games.
    assert not new_forecasts(g,[optional],[],kickoff+timedelta(minutes=1),
                             "2026-27","mens",30)
    # A one-sided prediction does not create a paired accuracy observation.
    assert scored_pairs(predicted[:1],results)[0].empty
    # Even if falsely inserted after start, invalid time is detected.
    corrupt=[dict(x) for x in predicted]
    corrupt[1]["forecast_created_utc"]=iso(kickoff+timedelta(seconds=1))
    assert scored_pairs(corrupt,results)[0].empty
    # An optional snapshot with a source hash from a superseded rating
    # file must fail closed; official archive remains independently usable.
    original_bytes=(base/"season_2026-27.csv.gz").read_bytes()
    changed=current.copy()
    changed.loc[0,"Home score"]=100
    changed.to_csv(base/"season_2026-27.csv.gz",index=False,compression="gzip")
    rejected,reason=load_optional(SPORT,root,NOW)
    assert rejected is None and "source hashes" in reason,reason
    # Restore source, but change status timestamp to simulate refresh race.
    (base/"season_2026-27.csv.gz").write_bytes(original_bytes)
    (base/"status.json").write_text(json.dumps({
        "snapshot_date":"2026-11-07",
        "updated_utc":(NOW-timedelta(minutes=15)).isoformat()
    }))
    rejected,reason=load_optional(SPORT,root,NOW)
    assert rejected is None and "changed" in reason,reason

latest=pd.DataFrame({"Team ID":["1","2"],"Current power":[20.,9.]})
history=pd.DataFrame({
    "Team ID":["1","2","1","2"],
    "Snapshot date":["2026-11-06","2026-11-06","2026-11-07","2026-11-07"],
    "Current power":[19.7,9.2,20.,9.]
})
movement=latest_movement(latest,history)
assert set(movement["Team ID"])=={"1","2"}
assert np.isclose(movement.loc[movement["Team ID"].eq("1"),"Since previous snapshot"].iloc[0],.3)
assert np.isclose(movement.loc[movement["Team ID"].eq("2"),"Since previous snapshot"].iloc[0],-.2)
assert set(movement["Previous snapshot date"])=={"2026-11-06"}
assert movement_for_team(history[history["Team ID"].eq("1")])==(0.3000000000000007,"2026-11-06")
no_prior=latest_movement(latest,history[history["Snapshot date"].eq("2026-11-07")])
assert no_prior.empty
mismatch=latest.copy()
mismatch.loc[0,"Current power"]=80.
check=latest_movement(mismatch,history)
assert np.isnan(check.loc[check["Team ID"].eq("1"),"Since previous snapshot"].iloc[0])
print("V233 anchored snapshot provenance, true pretip locks, valid pairs and movement history passed")

"""V209: append-only prospective cross-DI projections and result checks."""
from datetime import datetime,timezone,timedelta,date
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import pandas as pd

from prospective_cross_division_v209 import (
    utc_time,present_event,select_new_pairs,grade_pending,metrics,run,read_rows,MODEL_ID
)
from cross_division_v209 import estimate

now=datetime(2026,11,2,20,0,tzinfo=timezone.utc)
tip=datetime(2026,11,2,23,0,tzinfo=timezone.utc)
verified={str(n) for n in range(1,301)}
calibration={
    "model_version":"v209_empirical_prior_v1","sport":"mens-college-basketball",
    "source_season":"2025-26","training_games":541,
    "pooled_non_d1_rating":-24.0,"opponents":{},
}
def source_event(division,completed=False):
    d1="15"
    eid="401TESTM" if division=="mens-college-basketball" else "401TESTW"
    return {
        "id":eid,"date":"2026-11-02T23:00:00Z",
        "status":{"type":{"completed":completed,"state":"post" if completed else "pre"}},
        "competitions":[{"neutralSite":False,"competitors":[
            {"homeAway":"home","team":{"id":d1,"displayName":"Division I School"},"score":"80"},
            {"homeAway":"away","team":{"id":"99999","displayName":"Unverified Opponent"},"score":"50"},
        ]}],
    }

assert utc_time("bad") is None
assert present_event(source_event("mens-college-basketball"))["Status"]=="Scheduled"
assert present_event(source_event("mens-college-basketball",True))["Status"]=="Final"
sample=source_event("mens-college-basketball")
pred=select_new_pairs([sample],[],verified,{"15":4.5},calibration,now,
                      "mens","ratesha","sourcesha")
assert len(pred)==1
assert pred[0]["model_id"]==MODEL_ID
assert float(pred[0]["predicted_home_margin"])==31.5
assert len(select_new_pairs([sample],pred,verified,{"15":4.5},calibration,now,"mens","ratesha","sourcesha"))==0
assert not select_new_pairs([sample],[],verified,{"15":4.5},calibration,
                            tip-timedelta(minutes=20),"mens","r","c")
assert not select_new_pairs([sample],[],verified,{"15":4.5},calibration,
                            tip+timedelta(minutes=1),"mens","r","c")
assert not select_new_pairs([source_event("mens-college-basketball",True)],[],
                            verified,{"15":4.5},calibration,now,"mens","r","c")
assert not grade_pending(pred,[],{},now,"mens")
finished=grade_pending(pred,[],{date(2026,11,2):[source_event("mens-college-basketball",True)]},
                       tip+timedelta(minutes=30),"mens")
assert len(finished)==1 and int(finished[0]["actual_home_margin"])==30
assert metrics(pred,finished)["completed_paired_games"]==1
assert metrics(pred,finished)["margin_mae"]==1.5
assert metrics([],finished)["completed_paired_games"]==0
assert len(grade_pending(pred,finished,{date(2026,11,2):[source_event("mens-college-basketball",True)]},
                         tip+timedelta(hours=2),"mens"))==0
with TemporaryDirectory() as tmp:
    root=Path(tmp)
    for sport in ("mens-college-basketball","womens-college-basketball"):
        cpath=root/"data/cross_division"/f"{sport}_2025-26.json"
        cpath.parent.mkdir(parents=True,exist_ok=True)
        cpath.write_text(json.dumps({**calibration,"sport":sport}))
        rating=root/"data/ratings"/sport/"latest.csv.gz"
        rating.parent.mkdir(parents=True,exist_ok=True)
        pd.DataFrame([{"Team ID":"15","Current power":4.5}]).to_csv(rating,index=False,compression="gzip")
    state={"finished":False}
    def source(sport,day):
        if day==date(2026,11,2):
            return [source_event(sport,state["finished"])]
        return []
    def membership(sport,season=2027):
        assert season==2027
        return verified
    before=run(root,now=now,event_fetch=source,membership_fetch=membership)
    assert before["new_pregame_pairs"]==2 and before["saved_pregame_pairs"]==2
    before_bytes=(root/"data/cross_division_prospective/2026-27/forecasts.csv").read_bytes()
    duplicate=run(root,now=now+timedelta(minutes=1),event_fetch=source,membership_fetch=membership)
    assert duplicate["new_pregame_pairs"]==0
    assert (root/"data/cross_division_prospective/2026-27/forecasts.csv").read_bytes()==before_bytes
    state["finished"]=True
    after=run(root,now=tip+timedelta(hours=2),event_fetch=source,membership_fetch=membership)
    assert after["new_completed_results"]==2 and after["overall"]["completed_paired_games"]==2
    assert after["overall"]["margin_mae"]==1.5
    assert (root/"data/cross_division_prospective/2026-27/forecasts.csv").read_bytes()==before_bytes
    once=run(root,now=tip+timedelta(hours=3),event_fetch=source,membership_fetch=membership)
    assert once["new_completed_results"]==0
    assert len(read_rows(root/"data/cross_division_prospective/2026-27/results.csv"))==2
print("V209 distinct locked studies and append-only two-division final results passed")

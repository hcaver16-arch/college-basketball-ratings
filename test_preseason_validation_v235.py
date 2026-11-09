"""V235: source-date, prior-only, roster eligibility and pre-tip journal safety."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import numpy as np
import pandas as pd
from prospective_archive_v97 import iso
from preseason_validation_v235 import (
    build_preseason, pairs_for_completed, future_candidates,
    graded_pairs, metrics, describe_matchups, report_run,
    FORECAST_FIELDS, RESULT_FIELDS,
)

NOW=datetime(2026,11,9,18,tzinfo=timezone.utc)
SPORT="mens-college-basketball"
SOURCE_TIME="2026-10-27T02:39:48.578000Z"
def game(k,day,home,away,hs,aws,venue="Home",status="Final"):
    return {
        "Game ID":str(k),"Date":day,"Home ID":str(home),"Away ID":str(away),
        "Home":f"Home {home}","Away":f"Away {away}","Home score":hs,
        "Away score":aws,"Venue":venue,"Status":status,
    }
def eligible_row(i):
    return {
        "division":SPORT,"team_id":str(i),"data_available":True,
        "historical_boxscores_complete":True,"prior_roster_players":10,
        "current_players":12,"origin_coverage_fraction":.80,
        "confidence_weight":.80,"illustrative_adjustment_points":.1 if i%2 else -.2,
        "returning_minutes_pct_documented":45.,
        "incoming_prior_minutes_documented":320.,
    }
with TemporaryDirectory() as folder:
    root=Path(folder)
    ratings=root/"data"/"ratings"/SPORT
    ratings.mkdir(parents=True)
    experiment=root/"data"/"roster_experiment_v105"
    experiment.mkdir(parents=True)
    # 1,100 connected prior games ensure the true engine is used.
    previous=pd.DataFrame([game(10000+i,"2025-11-07",
        201+i%18,201+(i+7)%18,80+i%11,62+i%7)
        for i in range(1100)])
    previous.to_csv(ratings/"history_2025-26.csv.gz",index=False,compression="gzip")
    r=pd.DataFrame([eligible_row(i) for i in range(201,219)])
    r.loc[r["team_id"].eq("202"),"origin_coverage_fraction"]=.30
    r.loc[r["team_id"].eq("203"),"illustrative_adjustment_points"]=9.
    r.loc[r["team_id"].eq("204"),"data_available"]=False
    r.loc[r["team_id"].eq("205"),"prior_roster_players"]=2
    r.to_csv(experiment/f"{SPORT}_experimental_roster_sensitivity.csv",index=False)
    metadata={
        "version":105,"generated_at_utc":SOURCE_TIME,
        "status":"RESEARCH_ONLY_UNCALIBRATED_SENSITIVITY_NOT_A_PREDICTIVE_MODEL",
    }
    (experiment/"summary.json").write_text(json.dumps(metadata))
    models,source=build_preseason(root,SPORT,NOW)
    assert source["historical_games"]==1100
    assert source["qualified_roster_teams"]==14
    assert source["source_created_utc"].startswith("2026-10-27")
    m=models.set_index("Team ID")
    for tid in ("202","203","204","205"):
        assert not m.at[tid,"Qualified roster evidence"]
        assert pd.isna(m.at[tid,"V235 roster adjustment"])
        assert np.isclose(m.at[tid,"Roster scenario power"],
                          m.at[tid,"Baseline preseason power"])
    assert m.at["201","Qualified roster evidence"]
    assert np.isclose(m.at["201","Roster scenario power"],
                      m.at["201","Baseline preseason power"]+.1)
    # Historical results are used only as observations to score a frozen
    # prediction; none can enter the baseline or V105 evidence fit.
    played=pd.DataFrame([
        game(1,"2026-11-02",201,206,90,85),
        game(2,"2026-11-04",201,202,85,82), # disqualified opponent
        game(3,"2026-11-05",208,207,71,69,"Neutral"),
        game(4,"2026-11-06",208,207,None,None,status="Scheduled"),
    ])
    ids={str(i) for i in range(200,520)}
    retro=pairs_for_completed(played,models,ids)
    assert set(retro["game_id"])=={"1","3"}
    assert not retro["actual_home_margin"].isna().any()
    assert describe_matchups(retro)["matched_games"]==2
    result=metrics(retro,"baseline_home_margin")
    assert result["mae"]>=0 and result["games"]==2
    # No pre-tip forecast may be created after kickoff.
    start=NOW+timedelta(hours=6)
    upcoming={
        "f1":{
            "game_id":"f1","game_start_utc":iso(start),
            "home_id":"201","away_id":"206",
            "home_team":"Test A","away_team":"Test B",
            "final":False,"neutral":False
        },
        "f2":{
            "game_id":"f2","game_start_utc":iso(start),
            "home_id":"201","away_id":"202",
            "home_team":"Test A","away_team":"Unqualified",
            "final":False,"neutral":False
        },
    }
    new=future_candidates(NOW,upcoming,models,"mens",source,set(),ids)
    assert len(new)==1
    assert new[0]["game_id"]=="f1"
    assert new[0]["baseline_model_id"]!="official_saved_v97"
    assert abs((new[0]["baseline_home_margin"]+
        new[0]["home_roster_delta"]-new[0]["away_roster_delta"])-
        new[0]["roster_home_margin"])<1e-4
    # A missing roster or game result is not an imputed tie.
    assert graded_pairs(new,[]).empty
    saved=[{"division":"mens","game_id":"f1","status":"Final",
            "actual_home_margin":"7"}]
    pair=graded_pairs(new,saved)
    assert len(pair)==1
    assert len(graded_pairs(new,saved))==1
    bad=[dict(new[0])]
    bad[0]["forecast_created_utc"]=iso(start+timedelta(minutes=1))
    try:
        graded_pairs(bad,saved)
        raise AssertionError("After-tip forecast should have failed")
    except RuntimeError as exc:
        assert "after tipoff" in str(exc)
    assert not future_candidates(start+timedelta(minutes=1),upcoming,
        models,"mens",source,set(),ids)
    existing={("mens","f1")}
    assert not future_candidates(NOW,upcoming,models,"mens",source,existing,ids)

    # A roster file generated AFTER the first game must be rejected.
    # Source provenance cannot silently change under a locked model ID.
    # The archive must remain byte-for-byte untouched on mismatch.
    from unittest.mock import patch
    from prospective_archive_v97 import write_csv
    research=root/"data"/"preseason_research_v235"
    research.mkdir(parents=True)
    old_forecast=dict(new[0])
    old_forecast["source_sha256"]="prior-research-source-sha"
    write_csv(research/"first_forecasts.csv",[old_forecast],FORECAST_FIELDS)
    untouched=(research/"first_forecasts.csv").read_bytes()
    with patch("preseason_validation_v235.build_preseason",return_value=(models,source)):
        try:
            report_run(root,research,NOW,"track",
                scoreboard_reader=lambda sport,day: {},
                d1_reader=lambda sport: ids)
            raise AssertionError("Revised source silently reused immutable forecast ID")
        except RuntimeError as exc:
            assert "input changed" in str(exc)
    assert (research/"first_forecasts.csv").read_bytes()==untouched
    assert not (research/"results.csv").exists()
    # Updated post-opener roster timestamps are ineligible as frozen inputs.
    metadata["generated_at_utc"]="2026-11-03T00:00:00Z"
    (experiment/"summary.json").write_text(json.dumps(metadata))
    try:
        build_preseason(root,SPORT,NOW)
        raise AssertionError("Post-season-start roster source was accepted")
    except RuntimeError as exc:
        assert "pre-season" in str(exc)

print("V235 frozen-source validation, no invented team adjustments and immutable pretip tests passed")

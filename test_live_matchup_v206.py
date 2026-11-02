"""V206: real ESPN phase/clock, score-card safety, and archived pregame provenance."""
import ast
import csv
from pathlib import Path
from tempfile import TemporaryDirectory

from live_matchup_v206 import espn_progress, progress_label, score_pair, locked_pregame_forecast

def fixture(clock="12:36",period=2,status="Live"):
    return {"Game ID":"401900111","Home":"UTEP Miners","Away":"Northern Kentucky Norse",
            "Home ID":"2638","Away ID":"94","Status":status,
            "Home score":35 if status!="Scheduled" else None,
            "Away score":34 if status!="Scheduled" else None,
            "Game phase": "2nd half" if status=="Live" else None,
            "Game period":str(period),"Game clock":clock}

event={"status":{"type":{"state":"in","shortDetail":"2nd"},"period":2,"displayClock":"12:36"}}
phase=espn_progress(event,{}, "Live")
assert phase=={"Game period":"2","Game clock":"12:36","Game phase":"2nd half"},phase
game=fixture()
game.update(phase)
assert progress_label(game)=="2nd half · 12:36"
assert score_pair(game)==(34,35)
assert espn_progress(event,{},"Scheduled")=={"Game period":None,"Game clock":None,"Game phase":None}
assert espn_progress(event,{},"Final")=={"Game period":None,"Game clock":None,"Game phase":None}
assert progress_label(fixture(status="Scheduled"))=="Upcoming"
assert progress_label(fixture(status="Final"))=="Final"
assert score_pair(fixture(status="Scheduled")) is None
assert progress_label({"Status":"Live"})=="Live · game clock unavailable"
assert score_pair({"Away score":"?", "Home score":"35"}) is None
assert score_pair({"Away score":float("nan"), "Home score":0}) is None
assert score_pair({"Away score":-2, "Home score":0}) is None

half={"status":{"type":{"state":"in","shortDetail":"Halftime"},
       "period":1,"displayClock":"00:00"}}
assert espn_progress(half,{}, "Live")["Game phase"]=="Halftime"
assert espn_progress(half,{}, "Live")["Game clock"] is None
assert progress_label({"Status":"Live",**espn_progress(half,{}, "Live")})=="Halftime"
overtime={"status":{"period":4,"displayClock":"01:25","type":{"state":"in"}}}
assert espn_progress(overtime,{},"Live")["Game phase"]=="2OT"
invalid={"status":{"period":2,"displayClock":"arbitrary HTML <bad>" ,"type":{"state":"in"}}}
assert espn_progress(invalid,{},"Live")["Game clock"] is None

with TemporaryDirectory() as temp:
    root=Path(temp)
    folder=root/"data/prospective/2026-27"
    folder.mkdir(parents=True)
    fields=["game_id","division","model_id","home_id","away_id","forecast_created_utc",
            "game_start_utc","predicted_home_margin"]
    def write_rows(records):
        with (folder/"forecasts.csv").open("w",newline="",encoding="utf-8") as fd:
            out=csv.DictWriter(fd,fieldnames=fields)
            out.writeheader()
            out.writerows(records)
    rec={"game_id":"401900111","division":"mens","model_id":"official_saved_v97",
         "home_id":"2638","away_id":"94","forecast_created_utc":"2026-11-01T12:00:00Z",
         "game_start_utc":"2026-11-02T18:00:00Z","predicted_home_margin":"-5.2"}
    write_rows([rec])
    model=locked_pregame_forecast(game,"mens",root)
    assert model and model["margin"]==-5.2 and 0<model["probability"]<50
    assert "pregame" in model["source"]
    assert locked_pregame_forecast(game,"womens",root) is None
    assert locked_pregame_forecast({"Game ID":"bad","Home ID":"2638","Away ID":"94"},"mens",root) is None
    write_rows([{**rec,"forecast_created_utc":"2026-11-02T17:50:00Z"}])
    assert locked_pregame_forecast(game,"mens",root) is None
    write_rows([{**rec,"predicted_home_margin":"nan"}])
    assert locked_pregame_forecast(game,"mens",root) is None
    write_rows([{**rec,"home_id":"999"}])
    assert locked_pregame_forecast(game,"mens",root) is None
    write_rows([{**rec,"model_id":"unverified_roster_scenario"}])
    assert locked_pregame_forecast(game,"mens",root) is None

app_text=Path("app.py").read_text()
match_text=Path("matchup_analysis.py").read_text()
ast.parse(app_text)
ast.parse(match_text)
assert '"Game period", "Game clock", "Game phase"' in app_text
assert 'for col in ("Status", "Home score", "Away score", "Game period", "Game clock", "Game phase"):' in app_text
assert "espn_progress(event, competition, status)" in app_text
assert "progress_label(game) if status == \"Live\"" in app_text
assert 'archived=locked_pregame_forecast(game' in match_text
assert 'score_pair(game) if is_live or is_final else None' in match_text
assert "No adjustment" in match_text
assert "Same spread to one decimal" in match_text
assert "current game is excluded" in match_text
assert "Live score, period and clock come from ESPN" in match_text
assert "st.markdown(f\"### {away}" not in match_text
assert "Pregame home win estimate" in match_text
print("V206 live clock/score, first-locked pregame evidence, and presentation safety passed")

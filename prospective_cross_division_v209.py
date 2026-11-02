"""V209 prospective cross-division study, isolated from D1 ratings and V97 forecasts.

Append-only first eligible *future* projections are compared to official ESPN
finals. It does not backfill already played games, alter live lines or claim
that a later estimate was the historical pre-tip prediction.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from hashlib import sha256
from statistics import mean
import csv
import json
import math
import pandas as pd

from build_cross_division_v209 import get_day, ratings_membership, parse_final
from cross_division_v209 import estimate

ROOT=Path(__file__).resolve().parent
LEAGUES=("mens-college-basketball","womens-college-basketball")
FIELDS=["model_id","division","game_id","home_id","away_id",
        "home","away","game_start_utc","locked_utc",
        "predicted_home_margin","source_team_games","training_games",
        "ratings_sha256","calibration_sha256","source_label"]
RESULT_FIELDS=["division","game_id","game_start_utc","result_checked_utc",
               "home_score","away_score","actual_home_margin"]
MODEL_ID="cross_division_v209_experimental_v1"


def utc_time(value):
    try:
        t=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (TypeError,ValueError,OverflowError):
        return None


def read_rows(path):
    if not path.exists():return []
    with path.open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))


def append_rows(path,records,fields):
    if not records:return
    path.parent.mkdir(parents=True,exist_ok=True)
    already=path.exists() and path.stat().st_size>0
    with path.open("a",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields)
        if not already:w.writeheader()
        w.writerows(records)


def present_event(event):
    competitions=event.get("competitions") or [{}]
    c=competitions[0]
    teams=c.get("competitors") or []
    home=next((x for x in teams if x.get("homeAway")=="home"),None)
    away=next((x for x in teams if x.get("homeAway")=="away"),None)
    if not home or not away:return None
    start=utc_time(event.get("date"))
    if start is None:return None
    status=(event.get("status") or {}).get("type") or {}
    state="Final" if status.get("completed") else "Live" if status.get("state")=="in" else "Scheduled"
    return {
        "Game ID":str(event.get("id") or ""),
        "Home ID":str((home.get("team") or {}).get("id") or ""),
        "Away ID":str((away.get("team") or {}).get("id") or ""),
        "Home":str((home.get("team") or {}).get("displayName") or ""),
        "Away":str((away.get("team") or {}).get("displayName") or ""),
        "Venue":"Neutral" if c.get("neutralSite") is True else "Home",
        "Status":state, "start":start
    }


def select_new_pairs(events,existing,verified,ratings,calibration,now,division,ratings_sha,calib_sha):
    locked={(r.get("division"),r.get("game_id")) for r in existing}
    new=[]
    for e in events:
        g=present_event(e)
        if not g or not g["Game ID"] or g["Status"]!="Scheduled":
            continue
        if (division,g["Game ID"]) in locked:
            continue
        start=g["start"]
        if not timedelta(minutes=45)<=start-now<=timedelta(days=3):
            continue
        if not all(g.get(k) for k in ("Home ID","Away ID","Home","Away")):
            continue
        candidate=estimate(g,ratings,verified,calibration)
        if not candidate:continue
        new.append({
            "model_id":MODEL_ID,"division":division,
            "game_id":g["Game ID"],"home_id":g["Home ID"],"away_id":g["Away ID"],
            "home":g["Home"],"away":g["Away"],"game_start_utc":start.isoformat(),
            "locked_utc":now.isoformat(),
            "predicted_home_margin":candidate["home_margin"],
            "source_team_games":candidate["outside_games"],
            "training_games":candidate["history_games"],
            "ratings_sha256":ratings_sha,"calibration_sha256":calib_sha,
            "source_label":"2025-26 results / 2026-27 saved DI rating / outside-DI research model"
        })
        locked.add((division,g["Game ID"]))
    return new


def grade_pending(locked,scores,events_by_day,now,division):
    known={(r["division"],r["game_id"]) for r in scores}
    new=[]
    for f in locked:
        if f.get("division")!=division or (division,f.get("game_id")) in known:
            continue
        start=utc_time(f.get("game_start_utc"))
        if start is None or now<=start:continue
        day=start.astimezone(ZoneInfo("America/New_York")).date()
        for e in events_by_day.get(day,[]):
            if str(e.get("id"))!=f.get("game_id"):continue
            g=parse_final(e)
            if not g or g["Home ID"]!=f.get("home_id") or g["Away ID"]!=f.get("away_id"):
                continue
            new.append({"division":division,"game_id":f["game_id"],
                        "game_start_utc":f["game_start_utc"],"result_checked_utc":now.isoformat(),
                        "home_score":int(g["Home score"]),"away_score":int(g["Away score"]),
                        "actual_home_margin":int(g["Home score"]-g["Away score"])})
            known.add((division,f["game_id"]))
            break
    return new


def metrics(predictions,results):
    index={(r["division"],r["game_id"]):r for r in predictions}
    paired=[]
    for result in results:
        f=index.get((result["division"],result["game_id"]))
        if not f:continue
        try:
            prediction=float(f["predicted_home_margin"])
            actual=float(result["actual_home_margin"])
        except (TypeError,ValueError):continue
        if not math.isfinite(prediction) or not math.isfinite(actual):continue
        paired.append((prediction,actual))
    n=len(paired)
    return {
        "completed_paired_games":n,
        "margin_mae":round(mean(abs(p-a) for p,a in paired),3) if n else None,
        "winner_accuracy":round(sum((p>0)==(a>0) for p,a in paired if a!=0)/sum(a!=0 for _,a in paired),4) if any(a!=0 for _,a in paired) else None,
        "note":"Exploratory only; small samples are not proof of accuracy."
    }


def run(root=ROOT,now=None,event_fetch=get_day,membership_fetch=ratings_membership):
    now=now or datetime.now(timezone.utc)
    folder=root/"data/cross_division_prospective/2026-27"
    forecasts_path=folder/"forecasts.csv"
    results_path=folder/"results.csv"
    summary_path=folder/"summary.json"
    previous=read_rows(forecasts_path)
    finished=read_rows(results_path)
    new=[];new_results=[];issues=[]
    for sport in LEAGUES:
        division="mens" if sport.startswith("mens") else "womens"
        path=root/"data/cross_division"/f"{sport}_2025-26.json"
        rated=root/"data/ratings"/sport/"latest.csv.gz"
        if not path.is_file() or not rated.is_file():
            issues.append(sport+": missing archived calibration or rating snapshot")
            continue
        calibration=json.loads(path.read_text())
        if calibration.get("model_version")!="v209_empirical_prior_v1" or int(calibration.get("training_games",0))<30:
            issues.append(sport+": calibration has insufficient historical samples")
            continue
        frame=pd.read_csv(rated,compression="gzip",dtype={"Team ID":str})
        if not {"Team ID","Current power"}.issubset(frame.columns):
            issues.append(sport+": invalid saved ratings")
            continue
        ratings=frame.set_index("Team ID")["Current power"].to_dict()
        verified=membership_fetch(sport,season=2027)
        if not 300<=len(verified)<=450:
            issues.append(sport+": invalid verified membership size")
            continue
        source_days={now.date()+timedelta(days=i) for i in range(4)}
        # Resolve previous results for each explicitly locked game date. Do
        # not create or grade games that were never locked before tipoff.
        for row in previous:
            if row.get("division")!=division or (row.get("division"),row.get("game_id")) in {
                (r["division"],r["game_id"]) for r in finished}:
                continue
            d=utc_time(row.get("game_start_utc"))
            if d and d<now:
                source_days.add(d.astimezone(ZoneInfo("America/New_York")).date())
        events_by_day={}
        for day in sorted(source_days):
            events_by_day[day]=event_fetch(sport,day)
        events=[e for subset in events_by_day.values() for e in subset]
        added=select_new_pairs(events,previous+new,verified,ratings,calibration,now,division,
                              sha256(rated.read_bytes()).hexdigest(),sha256(path.read_bytes()).hexdigest())
        new.extend(added)
        new_results.extend(grade_pending(previous+new,finished+new_results,events_by_day,now,division))
    # Only append new source-observed rows. No rerating or mutation of first
    # historical forecast after its first saved pretip prediction.
    append_rows(forecasts_path,new,FIELDS)
    append_rows(results_path,new_results,RESULT_FIELDS)
    both=previous+new
    outcomes=finished+new_results
    report={
        "version":209,"model_id":MODEL_ID,"as_of_utc":now.isoformat(),
        "status":"EXPERIMENTAL_CROSS_DIVISION_NOT_OFFICIAL",
        "public_d1_ratings_modified":False,
        "new_pregame_pairs":len(new),"saved_pregame_pairs":len(both),
        "new_completed_results":len(new_results),
        "overall":metrics(both,outcomes),
        "mens":metrics([x for x in both if x["division"]=="mens"],
                       [x for x in outcomes if x["division"]=="mens"]),
        "womens":metrics([x for x in both if x["division"]=="womens"],
                         [x for x in outcomes if x["division"]=="womens"]),
        "issues":issues,
        "limitations":[
            "Game pair is locked only 45+ minutes before tipoff and after ESPN marks the game Scheduled.",
            "Both team IDs must be checked against ESPN's season-specific Division I conference membership.",
            "Research coefficients are based on last season's scoreboard results, not a prospectively validated 2026-27 model.",
            "No edits to existing DI-only rankings, NET, archived D1 pregame forecasts, or wagering markets."
        ]
    }
    folder.mkdir(parents=True,exist_ok=True)
    summary_path.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2),flush=True)
    return report


if __name__=="__main__":
    run()

"""V209 source-based empirical prior from ESPN 2025–26 cross-division games.

No guessed D2/D3 tiers. Opponents are identified as outside Courtside's
*verified D1 membership*, not asserted to be NCAA Division II/III.

2025-11-01 .. 2026-01-15: previous-season completed events. Both genders
are calibrated separately. Within the source season a time-ordered early
calibration / later diagnostic avoids direct cross-game training leakage.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import median
import json
import math
import requests
import pandas as pd

from rating_engine import calculate_power

ROOT=Path(__file__).resolve().parent
START=date(2025,11,1)
STOP=date(2026,1,15)
TRAIN_END="2025-12-15"
HCA=3.0
MIN_GAMES=30
HEADERS={"User-Agent":"Mozilla/5.0 CourtsideCrossDivision/1.0","Accept":"application/json"}
LEAGUES=["mens-college-basketball","womens-college-basketball"]


def get_day(sport,day):
    url=f"https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/scoreboard"
    resp=requests.get(url,params={"dates":day.strftime("%Y%m%d"),"groups":"50","limit":500},
                      headers=HEADERS,timeout=25)
    resp.raise_for_status()
    data=resp.json()
    if not isinstance(data.get("events"),list):
        raise ValueError("ESPN date feed without events list")
    return data["events"]


def parse_final(event):
    competition=(event.get("competitions") or [{}])[0]
    teams=competition.get("competitors") or []
    home=next((x for x in teams if x.get("homeAway")=="home"),None)
    away=next((x for x in teams if x.get("homeAway")=="away"),None)
    status=(event.get("status") or {}).get("type") or {}
    if not home or not away or not status.get("completed"):
        return None
    def score(c):
        value=c.get("score")
        if isinstance(value,dict):
            value=value.get("value",value.get("displayValue"))
        return float(value)
    try:
        hs,aws=score(home),score(away)
        hid,aid=str(home["team"]["id"]),str(away["team"]["id"])
        if not math.isfinite(hs) or not math.isfinite(aws) or not hid or not aid or hid==aid:
            return None
    except (TypeError,ValueError,KeyError):
        return None
    return {"Game ID":str(event.get("id") or ""),"Date":str(event.get("date") or "")[:10],
            "Home ID":hid,"Away ID":aid,
            "Home":str(home.get("team",{}).get("displayName") or hid),
            "Away":str(away.get("team",{}).get("displayName") or aid),
            "Home score":hs,"Away score":aws,"Status":"Final",
            "Venue":"Neutral" if competition.get("neutralSite") is True else "Home"}


def ratings_membership(sport):
    path=ROOT/"data"/"ratings"/sport/"latest.csv.gz"
    if not path.exists():
        raise RuntimeError(f"Missing existing Courtside D1 rating snapshot for {sport}")
    frame=pd.read_csv(path,compression="gzip",dtype={"Team ID":str})
    ids=set(frame["Team ID"].dropna().astype(str))
    if len(ids)<300:
        raise RuntimeError(f"{sport}: rated D1 snapshot has only {len(ids)} teams; refuse calibration")
    return ids


def implied_non_d1_strength(g,d1_ids,d1_power):
    home,away=g["Home ID"],g["Away ID"]
    if (home in d1_ids)==(away in d1_ids):
        return None
    is_home=home in d1_ids
    d1=home if is_home else away
    outside=away if is_home else home
    if d1 not in d1_power:
        return None
    d1_margin=(g["Home score"]-g["Away score"])*(1 if is_home else -1)
    d1_margin=max(-55.0,min(55.0,d1_margin))
    # d1 margin = d1 strength - opponent strength + (+3 if D1 home).
    # When D1 is away, venue adjustment is -3.
    other=float(d1_power[d1])+(HCA if is_home else -HCA if g["Venue"]=="Home" else 0)-d1_margin
    # Above formula must not give +3 to a DI home team on neutral courts.
    if g["Venue"]=="Neutral":
        other=float(d1_power[d1])-d1_margin
    if not math.isfinite(other):
        return None
    return outside,other


def fit_d1(games,d1_ids):
    both=[g for g in games if g["Home ID"] in d1_ids and g["Away ID"] in d1_ids]
    fitted,diagnostics=calculate_power(pd.DataFrame(both)) if both else (pd.DataFrame(),{})
    if fitted.empty:
        raise RuntimeError("No connected D1 games available to anchor cross-division strengths")
    return fitted.set_index("Team ID")["Power"].to_dict(),len(both)


def build_one(sport):
    verified=ratings_membership(sport)
    days=[START+timedelta(days=n) for n in range((STOP-START).days+1)]
    games=[];bad=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        future={pool.submit(get_day,sport,day):day for day in days}
        for f in as_completed(future):
            day=future[f]
            try:
                events=f.result()
                for e in events:
                    g=parse_final(e)
                    if g and g["Game ID"]:games.append(g)
            except Exception as exc:
                bad.append({"date":str(day),"error":str(exc)[:90]})
    if len(bad)>5:
        raise RuntimeError(f"{sport}: {len(bad)} ESPN daily feeds failed; no trustworthy empirical calibration")
    games=list({g["Game ID"]:g for g in games}.values())
    games.sort(key=lambda x:(x["Date"],x["Game ID"]))
    early=[g for g in games if g["Date"]<=TRAIN_END]
    # Time-ordered holdout: the D1 reference model is trained on EARLY games,
    # so later cross-division games are out-of-sample within the source season.
    early_power,early_d1_count=fit_d1(early,verified)
    implied_early=[]
    for game in early:
        x=implied_non_d1_strength(game,verified,early_power)
        if x:implied_early.append((game,x[0],x[1]))
    if len(implied_early)<MIN_GAMES:
        raise RuntimeError(f"{sport}: only {len(implied_early)} early cross-DI games")
    early_pool=median(v for _,_,v in implied_early)
    early_by=defaultdict(list)
    for _,oid,value in implied_early:early_by[oid].append(value)
    def prior(pool, values):
        if not values:return pool
        n=len(values)
        return pool+max(-12,min(12,(median(values)-pool)*n/(n+4.0)))
    holdout=[g for g in games if g["Date"]>TRAIN_END]
    errors_pool=[];errors_team=[]
    for g in holdout:
        x=implied_non_d1_strength(g,verified,early_power)
        if x is None:continue
        oid,truth=x
        # Difference in implied opponent rating equals difference in forecast
        # home margin: a transparent point-spread MAE diagnostic.
        errors_pool.append(abs(early_pool-truth))
        errors_team.append(abs(prior(early_pool,early_by[oid])-truth))
    # Deployment calibration uses all available LAST-SEASON historical games.
    # Nothing from 2026-27 outcomes enters this training set.
    full_power,full_d1_games=fit_d1(games,verified)
    all_others=defaultdict(list)
    used=0
    for game in games:
        x=implied_non_d1_strength(game,verified,full_power)
        if not x:continue
        oid,raw=x
        all_others[oid].append(raw); used+=1
    all_values=[v for vals in all_others.values() for v in vals]
    if len(all_values)<MIN_GAMES:
        raise RuntimeError("Insufficient cross-div source games")
    pool=float(median(all_values))
    opponents={}
    for oid,vals in sorted(all_others.items()):
        opponents[oid]={"games":len(vals),"shrunk_rating":round(prior(pool,vals),3)}
    result={
        "model_version":"v209_empirical_prior_v1",
        "sport":sport,"source_season":"2025-26",
        "source_cutoff_utc":"2026-04-15T00:00:00Z",
        "collection_window_start":str(START),"collection_window_end":str(STOP),
        "verified_d1_team_ids":len(verified),
        "final_games_processed":len(games),"d1_games_fitted":full_d1_games,
        "training_games":used,"opponents_with_historical_games":len(opponents),
        "pooled_non_d1_rating":round(pool,3),
        "opponents":opponents,
        "time_split_diagnostic":{
            "train_through":TRAIN_END,
            "train_d1_games":early_d1_count,
            "train_cross_division_games":len(implied_early),
            "holdout_cross_division_games":len(errors_team),
            "pooled_margin_MAE":round(sum(errors_pool)/len(errors_pool),2) if errors_pool else None,
            "team_shrunk_margin_MAE":round(sum(errors_team)/len(errors_team),2) if errors_team else None,
            "note":"Out-of-sample *within 2025-26* using early season ratings. Does not validate 2026-27 forecast performance."
        },
        "failed_source_dates":bad,
        "notes":[
            "Provisional pooled strength for teams outside Courtside's verified D1 membership; not proof of D2, D3, NAIA category.",
            "Team historical results are strongly shrunk toward pooled median; unknown opponents receive the pooled prior.",
            "Prior-season team power and current-season D1 power are assumed to share an approximate centered scale. Not yet calibrated out of sample for 2026-27.",
            "Not a betting line, live in-game probability or official D1 model forecast.",
            "Data excludes all 2026-27 scores; no future outcome leakage into training.",
            "Historical margins are clipped at +/-55 before inferring strengths. Historical D1 power is a separate ridge-fitted network."
        ]
    }
    path=ROOT/"data"/"cross_division"/f"{sport}_2025-26.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2)+"\n")
    print(sport, {k:result[k] for k in ("verified_d1_team_ids","training_games","opponents_with_historical_games","pooled_non_d1_rating","time_split_diagnostic")},flush=True)
    return result


if __name__=="__main__":
    for sport in LEAGUES:build_one(sport)

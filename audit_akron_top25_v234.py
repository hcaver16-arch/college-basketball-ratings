"""V234 read-only investigation: why does Akron appear in Courtside's top 25?

Reports live saved power, previous-season baseline, actual current results,
opponent strength, real D1-only rank and effects of the last game. Never
modifies published ratings, roster effects or archived predictions.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from rating_engine import calculate_power, make_combined
from prior_transition_research_v229 import anchored_ridge, normalize

SPORT="mens-college-basketball"
ROOT=Path(__file__).resolve().parent
TARGET_NAME="akron"


def calc(sport=SPORT,base=ROOT):
    path=base/"data"/"ratings"/sport
    saved=pd.read_csv(path/"latest.csv.gz", dtype={"Team ID":str})
    prior_results=pd.read_csv(path/"history_2025-26.csv.gz", dtype={"Home ID":str,"Away ID":str,"Game ID":str})
    current_results=pd.read_csv(path/"season_2026-27.csv.gz",dtype={"Home ID":str,"Away ID":str,"Game ID":str})
    snapshots=pd.read_csv(path/"history.csv.gz",dtype={"Team ID":str})
    prior,s1=calculate_power(prior_results)
    oncourt,s2=calculate_power(current_results)
    combined=make_combined(prior,oncourt,{})
    prior=prior.assign(**{"Team ID":prior["Team ID"].astype(str)})
    oncourt=oncourt.assign(**{"Team ID":oncourt["Team ID"].astype(str)})
    saved["Team ID"]=saved["Team ID"].astype(str)
    akron=saved[saved["Team"].astype(str).str.contains("Akron",case=False,na=False)]
    if len(akron)!=1: raise RuntimeError("Expected 1 Akron team row in saved official men's ratings; got "+str(len(akron)))
    ar=akron.iloc[0].to_dict()
    target=str(ar["Team ID"])
    # Fetch ESPN's current conference-membership list exactly like Rankings UI.
    from reliability_v99 import fetch_d1_membership
    ids=set(map(str,fetch_d1_membership(sport)))
    if len(ids)<200:raise RuntimeError("D1 membership incomplete")
    official_d1=saved[saved["Team ID"].isin(ids)].sort_values("Current power",ascending=False).reset_index(drop=True)
    prior_d1=prior[prior["Team ID"].isin(ids)].sort_values("Power",ascending=False).reset_index(drop=True)
    idx=official_d1.index[official_d1["Team ID"].eq(target)].tolist()
    if len(idx)!=1:raise RuntimeError("Akron absent from verified current D1 rankings")
    rank=int(idx[0]+1)
    start_rank_idx=prior_d1.index[prior_d1["Team ID"].eq(target)].tolist()
    start_rank=(int(start_rank_idx[0]+1) if len(start_rank_idx)==1 else None)
    latest=float(ar["Current power"])
    baseline=float(ar["Preseason rating"])
    old=prior[prior["Team ID"].eq(target)]
    fitted=oncourt[oncourt["Team ID"].eq(target)]
    assert not old.empty and not fitted.empty
    assert abs(float(old.iloc[0]["Power"])-baseline)<.03
    assert abs(float(fitted.iloc[0]["Power"])-float(ar["On-court rating"]))<.03
    assert abs(latest-float(combined[combined["Team ID"].eq(target)].iloc[0]["Current power"]))<.04
    current_finals=normalize(current_results,"current").copy()
    previous_finals=normalize(prior_results,"prior").copy()
    def games_for(g):
        v=g[(g["Home ID"].eq(target)) | (g["Away ID"].eq(target))].copy()
        out=[]
        for _, row in v.iterrows():
            home=(str(row["Home ID"])==target)
            oppid=str(row["Away ID"] if home else row["Home ID"])
            oppname=str(row["Away"] if home else row["Home"])
            scores=[float(row["Home score"]),float(row["Away score"])]
            margin=(scores[0]-scores[1])*(1 if home else -1)
            opprow=saved.loc[saved["Team ID"].eq(oppid)]
            p=prior[prior["Team ID"].eq(oppid)]
            out.append({
                "date":str(row["Date"]),"game_id":str(row["Game ID"]),
                "opponent":oppname,"opponent_id":oppid,"opponent_d1_verified":oppid in ids,
                "location":"home" if home else ("neutral" if row["Venue"]=="Neutral" else "away"),
                "result":"W" if margin>0 else ("L" if margin<0 else "T"),
                "akron_score":scores[0] if home else scores[1],
                "opponent_score":scores[1] if home else scores[0],
                "actual_margin":margin,
                "margin_after_cap":float(np.clip(margin,-40,40)),
                "opponent_prior_power":float(p.iloc[0]["Power"]) if len(p) else None,
                "opponent_current_power":float(opprow.iloc[0]["Current power"]) if len(opprow) else None,
            })
        return sorted(out,key=lambda x:(x["date"],x["game_id"]))
    current_games=games_for(current_finals)
    last_games=games_for(previous_finals)
    if len(current_games)!=int(ar["Games played"]):raise RuntimeError("Games played disagrees with saved finals")
    earlier=snapshots[snapshots["Team ID"].eq(target)].copy()
    earlier["Snapshot date"]=earlier["Snapshot date"].astype(str)
    earlier=earlier.drop_duplicates("Snapshot date",keep="last").sort_values("Snapshot date")
    history=[{"date":str(r["Snapshot date"]),"power":float(r["Current power"]),"games":int(r["Games played"])}
             for _,r in earlier.iterrows()]
    # Separate out mathematical support from an alternative *after games* fit.
    priormap=dict(zip(prior["Team ID"].astype(str),prior["Power"].astype(float)))
    research=anchored_ridge(priormap,current_finals)
    anchored_d1=sorted(
        ((tid,float(value)) for tid,value in research.items() if tid in ids),
        key=lambda x:x[1], reverse=True
    )
    anchored_rank=next(i+1 for i,(tid,_) in enumerate(anchored_d1) if tid==target)
    anchored_25_cutoff=anchored_d1[24][1]
    # Additional public sanity check: leave only prior season (no 2026-27):
    # historical preseason rank from last-season score margins may be inflated
    # due to all-non-D1 opponents and tight conference loops.
    top25=official_d1.head(25).copy()
    return {
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "sport":sport,"saved_snapshot_status":json.loads((path/"status.json").read_text()),
        "akron":{
            "name":str(ar["Team"]),"id":target,"verified_D1":True,
            "official_rank_from_all_teams":int(ar["Rank"]),
            "verified_d1_rank":rank,
            "preseason_d1_rank":start_rank,
            "current_power":round(latest,3),
            "preseason_power":round(baseline,3),
            "change_vs_preseason":round(latest-baseline,3),
            "on_court_fit":round(float(ar["On-court rating"]),3),
            "current_weight":round(float(ar["On-court weight"]),3),
            "games_played":int(ar["Games played"]),
            "current_wins":sum(x["result"]=="W" for x in current_games),
            "current_losses":sum(x["result"]=="L" for x in current_games),
            "anchored_candidate_after_games":round(float(research.get(target,float("nan"))),3),
            "anchored_research_only_d1_rank":anchored_rank,
            "prior_2025_26_games":len(last_games),
            "prior_2025_26_wins":sum(x["result"]=="W" for x in last_games),
            "prior_2025_26_losses":sum(x["result"]=="L" for x in last_games),
            "prior_non_D1_games":sum(not x["opponent_d1_verified"] for x in last_games),
        },
        "d1_rank_25_cutoff_power":round(float(official_d1.iloc[24]["Current power"]),3),
        "preseason_rank25_cutoff":round(float(prior_d1.iloc[24]["Power"]),3),
        "anchored_research_only_rank25_cutoff":round(float(anchored_25_cutoff),3),
        "akron_current_games_prior_based_expected_margin":([
            {
                "opponent":g["opponent"],
                "expected_akron_margin_using_preseason_strength":round(
                    baseline-float(g["opponent_prior_power"]) +
                    (3 if g["location"]=="home" else (-3 if g["location"]=="away" else 0)),3
                ),
                "actual_akron_margin":g["actual_margin"]
            } for g in current_games if g["opponent_prior_power"] is not None
        ]),
        "top25_snapshot":[
            {"rank":i+1,"team":str(r["Team"]),"power":round(float(r["Current power"]),2),
             "preseason":round(float(r["Preseason rating"]),2),
             "games":int(r["Games played"])}
            for i,(_,r) in enumerate(top25.iterrows())],
        "akron_current_games":current_games,
        "akron_previous_season_games":last_games,
        "akron_ratings_history":history,
        "math":{
            "formula":"(1 - current_weight) * preseason_power + current_weight * on_court_fit",
            "published_power_recomputed":round((1-float(ar["On-court weight"]))*baseline +
               float(ar["On-court weight"])*float(ar["On-court rating"]),3),
            "current_inseason_fit_regularization":"ridge = 8 toward 0, cap margins at +/-40, home advantage 3",
            "missing_roster_adjustments":True,
            "note":"2025-26 prior used as the 2026-27 opening rating without roster/coach turnover calibration",
        },
    }

if __name__=="__main__":
    answer=calc()
    print("V234_AKRON_AUDIT_START")
    print(json.dumps(answer,indent=2))
    print("V234_AKRON_AUDIT_END")

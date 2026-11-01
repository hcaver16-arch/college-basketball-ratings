"""Read-only, deterministic rating and pregame archive validation.

Run: python validate_model_v180.py
No production files are written or prediction formulas modified.
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from rating_engine import calculate_power, blending_weight, make_combined

def fixture(n):
    return pd.DataFrame([{
        "Game ID": str(i), "Status": "Final",
        "Home ID": str(100 + i % 6), "Away ID": str(100 + (i+1) % 6),
        "Home": f"Home{i%6}", "Away": f"Away{(i+1)%6}",
        "Home score": 75+i%5, "Away score": 69+i%3,
        "Venue": "Neutral" if i%2 else "Home",
    } for i in range(n)])

def test_boundaries():
    counts={}
    for n in [0,1,19,20,25]:
        ratings,meta=calculate_power(fixture(n))
        assert meta["games"]==n, (n,meta)
        assert bool(ratings.empty) == (n<20), n
        counts[str(n)]={"eligible":meta["games"],"fitted_teams":meta["teams"]}
    return counts

def test_filters():
    base=fixture(20)
    duplicate=pd.concat([base,base.iloc[[0]]],ignore_index=True)
    assert calculate_power(duplicate)[1]["games"]==20
    pending=base.iloc[[0]].copy();pending["Game ID"]="future";pending["Status"]="Scheduled"
    mixed=pd.concat([base,pending],ignore_index=True)
    assert calculate_power(mixed)[1]["games"]==20
    return "PASS: duplicates, future games excluded"

def test_blending():
    expected={0:0.0,5:.35,10:.65,15:.85,20:.95,25:1.0,30:1.0}
    for n,v in expected.items():
        assert abs(blending_weight(n)-v)<1e-9,(n,blending_weight(n))
    prior=pd.DataFrame([{"Team ID":"100","Team":"Test","Power":10.0}])
    current=pd.DataFrame([{"Team ID":"100","Team":"Test","Power":2.0,"Games":5}])
    combined=make_combined(prior,current,{})
    expected_power=.65*10+.35*2
    assert abs(combined.iloc[0]["Current power"]-expected_power)<1e-9
    return "PASS: prior weights and combined rating"

def diagnostic_risks():
    findings=[]
    mixed=fixture(20)
    mixed["Home ID"]=mixed["Home ID"].astype(int)
    mixed["Away ID"]=mixed["Away ID"].astype(int)
    try:
        calculate_power(mixed)
        findings.append("Mixed ID type: numeric-only sample completed; inspect type normalization separately")
    except (KeyError,TypeError,ValueError) as exc:
        findings.append(f"KNOWN RISK: numeric team IDs trigger {type(exc).__name__}; upstream string normalization is required")
    odd=fixture(20)
    odd["Venue"]="Unknown"
    _,base=calculate_power(odd)
    findings.append("VENUE RISK: existing engine treats every value other than exact 'Neutral' as home advantage")
    return findings

def archive_checks():
    result={}
    for sport in ["mens-college-basketball","womens-college-basketball"]:
        path=Path("data/predictions")/sport/"first_forecasts.csv.gz"
        if not path.exists():
            result[sport]={"status":"MISSING"}
            continue
        df=pd.read_csv(path,compression="gzip",dtype={"Game ID":str})
        required={"Game ID","First forecast UTC","Game start UTC"}
        if not required.issubset(df.columns):
            result[sport]={"status":"MISSING REQUIRED COLUMNS","columns":sorted(required-set(df.columns))}
            continue
        start=pd.to_datetime(df["Game start UTC"],utc=True,errors="coerce")
        forecast=pd.to_datetime(df["First forecast UTC"],utc=True,errors="coerce")
        missing=int((start.isna()|forecast.isna()).sum())
        after=int(((forecast>=start)&start.notna()&forecast.notna()).sum())
        dup=int(df["Game ID"].duplicated().sum())
        result[sport]={"rows":len(df),"duplicate_game_ids":dup,"missing_timestamps":missing,"not_before_tipoff":after}
        assert dup==0, f"{sport}: duplicate locked forecast IDs"
        assert missing==0, f"{sport}: invalid forecast timestamps"
        assert after==0, f"{sport}: non-pregame forecasts"
    return result

def main():
    report={"rating_thresholds":test_boundaries(),"filter_tests":test_filters(),
            "blending":test_blending(),"risks":diagnostic_risks(),
            "first_forecast_archive":archive_checks(),
            "scope":"Validation only; no predictions or ratings modified"}
    print(json.dumps(report,indent=2))
if __name__=="__main__": main()

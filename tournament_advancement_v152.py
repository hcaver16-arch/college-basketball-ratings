"""Exact probability propagation through Courtside's hypothetical 76-team bracket.

This is an illustrative neutral-site rating scenario, NOT a calibrated tournament
forecast. Each Opening Round slot is a probability distribution, not a fake team.
"""
from __future__ import annotations
import math
import re
import pandas as pd

MARGIN_SD=11.0
STAGES=("Reach R64","Reach R32","Reach Sweet 16","Reach Elite Eight",
        "Reach Final Four","Reach Championship","Win championship")


def win_probability(a,b):
    return 0.5*(1+math.erf((a-b)/(MARGIN_SD*math.sqrt(2))))


def _meet(left,right,powers):
    """Independent-distribution matchup resulting winner probability masses."""
    results={}
    for a,pa in left.items():
        for b,pb in right.items():
            p=pa*pb
            awin=win_probability(powers[a],powers[b])
            results[a]=results.get(a,0.0)+p*awin
            results[b]=results.get(b,0.0)+p*(1-awin)
    return results


def advancement_probabilities(payload):
    teams=payload["teams"]
    powers={name:float(info["power"]) for name,info in teams.items()}
    results={name:{stage:0.0 for stage in STAGES} for name in teams}
    opening={int(g["game"]):g for g in payload["opening"]}

    def slot_distribution(name):
        if name in teams:
            return {name:1.0}
        match=re.match(r"^Winner OR(\d+):",name)
        if match is None:
            raise ValueError(f"Unrecognized Opening Round slot: {name}")
        game=opening[int(match.group(1))]
        a,b=game["a"],game["b"]
        pa=win_probability(powers[a],powers[b])
        return {a:pa,b:1-pa}

    def record(round_name, groups):
        for dist in groups:
            for name,p in dist.items():
                results[name][round_name]+=p

    region_winners={}
    for region in payload["regions"]:
        entrants=[slot_distribution(game[side]) for game in region["games"] for side in ("a","b")]
        if len(entrants)!=16:
            raise ValueError("Region must contain exactly 16 opening slots")
        record("Reach R64",entrants)
        # R64 -> 8 winners, R32 -> 4, Sweet 16 -> 2, Elite Eight -> 1
        current=entrants
        for stage in ("Reach R32","Reach Sweet 16","Reach Elite Eight","Reach Final Four"):
            current=[_meet(current[i],current[i+1],powers) for i in range(0,len(current),2)]
            record(stage,current)
        region_winners[region["name"]]=current[0]
    # An illustrative neutral-site Final Four layout, not an official NCAA pairing.
    pairs=(("East","West"),("South","Midwest"))
    finalists=[_meet(region_winners[a],region_winners[b],powers) for a,b in pairs]
    record("Reach Championship",finalists)
    champions=_meet(finalists[0],finalists[1],powers)
    record("Win championship",[champions])
    # Probability flow invariants: 64 R64, 32 R32, 16 S16, 8 E8, 4 F4, 2 title game, 1 champ.
    expected=(64,32,16,8,4,2,1)
    for stage,count in zip(STAGES,expected):
        total=sum(row[stage] for row in results.values())
        if not math.isclose(total,count,abs_tol=1e-8):
            raise AssertionError(f"{stage} probability flow: {total} != {count}")
    return results


def render_advancement(payload):
    import streamlit as st
    st.markdown("### Tournament advancement probabilities · Experimental")
    st.caption("Exact matchup probability propagation through the current hypothetical 76-team bracket, including all 12 Opening Round outcomes. Uses independent neutral-court games and the existing 11-point margin assumption. NOT calibrated, and not official selection probabilities.")
    try:
        chances=advancement_probabilities(payload)
    except (ValueError,KeyError,AssertionError) as exc:
        st.warning(f"Advancement scenario unavailable: {exc}")
        return
    rows=[{"Team":name,"Conference":payload["teams"][name]["conference"],
           "Overall order":payload["teams"][name]["overall"],**{k:100*v for k,v in chances[name].items()}}
          for name in chances]
    frame=pd.DataFrame(rows).sort_values("Win championship",ascending=False)
    region=st.selectbox("Advancement view",["All projected teams"]+[r["name"] for r in payload["regions"]],key="v152_region")
    if region!="All projected teams":
        selected=set()
        matching=next(r for r in payload["regions"] if r["name"]==region)
        for g in matching["games"]:
            for side in ("a","b"):
                name=g[side]
                if name in chances:
                    selected.add(name)
                else:
                    m=re.match(r"^Winner OR(\d+):",name)
                    if m:
                        opening=next(x for x in payload["opening"] if x["game"]==int(m.group(1)))
                        selected.update((opening["a"],opening["b"]))
        frame=frame[frame["Team"].isin(selected)]
    st.dataframe(frame,hide_index=True,use_container_width=True,column_config={
        key:st.column_config.ProgressColumn(key,format="%.1f%%",min_value=0,max_value=100)
        for key in STAGES},column_order=["Overall order","Team","Conference",*STAGES])
    st.caption("Each percentage is conditional on the entire modeled Opening Round and bracket; later round outcomes use ratings unchanged by previous wins. Full model validation and NCAA placement constraints remain future work.")

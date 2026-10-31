"""V138 preseason bracketology sandbox: 76 teams, 32 projected AQs, 44 at-large.

Not NCAA committee selections, calibrated probabilities, or earned conference bids.
Power rating is only a provisional proxy while resume metrics are being validated.
"""
from __future__ import annotations
import pandas as pd
import streamlit as st

FIELD = 76
AUTO = 32
AT_LARGE = 44

def project_field(ratings, verified_d1_ids):
    needed={"Team ID","Team","Conference","Current power"}
    if not isinstance(ratings,pd.DataFrame) or not needed.issubset(ratings.columns):
        return pd.DataFrame(), "Saved team rankings or conference identities unavailable"
    data=ratings.copy()
    data["Team ID"]=data["Team ID"].astype(str)
    data["Current power"]=pd.to_numeric(data["Current power"],errors="coerce")
    data=data[data["Team ID"].isin(set(map(str,verified_d1_ids)))].dropna(subset=["Team","Conference","Current power"])
    data=data[~data["Conference"].astype(str).str.contains("Unassigned|not verified|Unknown|non-D1",case=False,na=False)]
    data=data.sort_values(["Current power","Team ID"],ascending=[False,True]).drop_duplicates("Team ID")
    conferences=data["Conference"].nunique()
    if conferences != AUTO:
        return pd.DataFrame(), f"Found {conferences} verified conference labels, but the 2027 field requires {AUTO}. Projection withheld to avoid invented automatic bids."
    # Highest-rated team per conference is a placeholder, not a real tournament champion.
    automatic=data.drop_duplicates("Conference").copy()
    automatic["Bid type"]="Projected automatic (power proxy)"
    remaining=data[~data["Team ID"].isin(automatic["Team ID"])]
    atlarge=remaining.head(AT_LARGE).copy()
    atlarge["Bid type"]="Projected at-large (power proxy)"
    field=pd.concat([automatic,atlarge],ignore_index=True)
    if len(automatic)!=AUTO or len(atlarge)!=AT_LARGE or len(field)!=FIELD:
        return pd.DataFrame(), "Insufficient eligible verified teams for a complete projection"
    field=field.sort_values(["Current power","Team ID"],ascending=[False,True]).reset_index(drop=True)
    field["Overall seed list"]=range(1,FIELD+1)
    # 76 teams advance through an Opening Round to a 64-team first round.
    # Do not invent official region placements or bracket slots.
    field["Opening Round (proxy)"]=False
    # NCAA: 12 lowest-seeded AQs and 12 lowest-seeded at-larges.
    for bid, n in [("Projected automatic (power proxy)",12),("Projected at-large (power proxy)",12)]:
        ids=field.loc[field["Bid type"].eq(bid)].tail(n).index
        field.loc[ids,"Opening Round (proxy)"]=True
    return field,None

def render_bracketology(ratings,verified_d1_ids,league):
    st.subheader("2027 NCAA tournament projection · Early preview")
    st.caption(f"{league}: 76-team provisional field — 32 projected conference qualifiers and 44 at-large teams. Selection Sunday committee decisions are not modeled.")
    frame,error=project_field(ratings,verified_d1_ids)
    if error:
        st.warning(error)
        return
    st.info("This first version is a **power-rating-only scenario**, not a validated bracketology model. Conference qualifiers are hypothetical highest-rated teams, not tournament winners. Do not interpret seed order or opening-round placement as an NCAA prediction.")
    a,b,c=st.columns(3)
    a.metric("Projected field",len(frame))
    b.metric("Conference slots",int(frame["Bid type"].str.startswith("Projected automatic").sum()))
    c.metric("Opening Round teams",int(frame["Opening Round (proxy)"].sum()))
    view=st.radio("Show teams",["All 76","Projected automatic bids","Projected at-large bids","Opening Round"],horizontal=True,key="v138_filter")
    shown=frame
    if view=="Projected automatic bids":shown=shown[shown["Bid type"].str.startswith("Projected automatic")]
    elif view=="Projected at-large bids":shown=shown[shown["Bid type"].str.startswith("Projected at-large")]
    elif view=="Opening Round":shown=shown[shown["Opening Round (proxy)"]]
    st.dataframe(shown[["Overall seed list","Team","Conference","Current power","Bid type","Opening Round (proxy)"]],hide_index=True,use_container_width=True)
    with st.expander("Model assumptions and limitations"):
        st.write("The field is an illustrative scenario based only on Courtside power ratings and verified D1 conference labels. It ignores NET, strength of record, quadrant wins, committee selection criteria, eligibility changes, and conference tournament results. No automatic bid is officially secured. Overall seed list is only a power-based ordering, not regional seeding.")

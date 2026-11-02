"""V138 preseason bracketology sandbox: 76 teams, 32 projected AQs, 44 at-large.

Not NCAA committee selections, calibrated probabilities, or earned conference bids.
Power ratings are the fallback where provisional SOR is not eligible; this is an uncalibrated selection scenario.
"""
from __future__ import annotations
import pandas as pd
import streamlit as st
from tournament_resume_v139 import add_resume
from tournament_native_v142 import render_native_bracket

FIELD = 76
AUTO = 32
AT_LARGE = 44

def project_field(ratings, verified_d1_ids, sor=None):
    needed={"Team ID","Team","Conference","Current power"}
    if not isinstance(ratings,pd.DataFrame) or not needed.issubset(ratings.columns):
        return pd.DataFrame(), "Saved team rankings or conference identities unavailable"
    data=ratings.copy()
    data["Team ID"]=data["Team ID"].astype(str)
    data["Current power"]=pd.to_numeric(data["Current power"],errors="coerce")
    data=data[data["Team ID"].isin(set(map(str,verified_d1_ids)))].dropna(subset=["Team","Conference","Current power"])
    data=data[~data["Conference"].astype(str).str.contains("Unassigned|not verified|Unknown|non-D1",case=False,na=False)]
    data=data.sort_values(["Current power","Team ID"],ascending=[False,True]).drop_duplicates("Team ID")
    data=add_resume(data,sor)
    data=data.sort_values(["Selection score","Current power","Team ID"],ascending=[False,False,True])
    conferences=data["Conference"].nunique()
    if conferences != AUTO:
        return pd.DataFrame(), f"Found {conferences} verified conference labels, but the 2027 field requires {AUTO}. Projection withheld to avoid invented automatic bids."
    # Highest-rated team per conference is a placeholder, not a real tournament champion.
    automatic=data.drop_duplicates("Conference").copy()
    automatic["Bid type"]="Projected automatic (scenario)"
    remaining=data[~data["Team ID"].isin(automatic["Team ID"])]
    atlarge=remaining.head(AT_LARGE).copy()
    atlarge["Bid type"]="Projected at-large (scenario)"
    field=pd.concat([automatic,atlarge],ignore_index=True)
    if len(automatic)!=AUTO or len(atlarge)!=AT_LARGE or len(field)!=FIELD:
        return pd.DataFrame(), "Insufficient eligible verified teams for a complete projection"
    field=field.sort_values(["Selection score","Current power","Team ID"],ascending=[False,False,True]).reset_index(drop=True)
    field["Overall seed list"]=range(1,FIELD+1)
    # 76 teams advance through an Opening Round to a 64-team first round.
    # Do not invent official region placements or bracket slots.
    field["Opening Round (proxy)"]=False
    # NCAA: 12 lowest-seeded AQs and 12 lowest-seeded at-larges.
    for bid, n in [("Projected automatic (scenario)",12),("Projected at-large (scenario)",12)]:
        ids=field.loc[field["Bid type"].eq(bid)].tail(n).index
        field.loc[ids,"Opening Round (proxy)"]=True
    return field,None

def render_bracketology(ratings,verified_d1_ids,league,sor=None):
    """V197: bracket-first layout with dedicated field, advancement and site tabs."""
    st.markdown("""<style>
    .cs197-intro{margin:2px 0 10px}
    .cs197-intro h2{margin:0;color:#193a70;font-size:1.55rem}
    .cs197-intro p{font-size:.83rem;color:#667c98;margin:4px 0 0}
    .st-key-cs197_tournament [data-testid="stTabs"] [role="tablist"]{
        gap:6px;flex-wrap:wrap;border-bottom:1px solid #d7e2f2}
    .st-key-cs197_tournament [data-testid="stTabs"] [role="tab"]{
        font-weight:750;font-size:.87rem}
    .st-key-cs197_tournament [data-testid="stMetric"]{
        border:1px solid #d6e2f3;border-radius:10px;padding:10px 14px;
        background:#f6f9fe}
    @media(max-width:700px){.cs197-intro h2{font-size:1.2rem}}
    </style>""", unsafe_allow_html=True)
    with st.container(key="cs197_tournament"):
        st.markdown(
            '<div class="cs197-intro"><h2>2027 NCAA Tournament Projections</h2>'
            '<p>Courtside scenario · Independent of official NCAA selections</p></div>',
            unsafe_allow_html=True
        )
        frame,error=project_field(ratings,verified_d1_ids,sor)
        if error:
            st.warning(error)
            return
        k1,k2,k3,k4=st.columns(4,gap="small")
        k1.metric("Projected teams",len(frame))
        k2.metric("Automatic bids",int(frame["Bid type"].str.startswith("Projected automatic").sum()))
        k3.metric("At-large bids",int(frame["Bid type"].str.startswith("Projected at-large").sum()))
        k4.metric("Opening games",int(frame["Opening Round (proxy)"].sum())//2)
        bracket_tab, field_tab, advancement_tab, locations_tab = st.tabs(
            ["Bracket", "Projected Field", "Advancement", "Locations"]
        )
        with bracket_tab:
            st.caption(
                "Hypothetical bracket and matchups, not official NCAA placements. "
                "Game probabilities use uncalibrated neutral-court power ratings."
            )
            render_native_bracket(frame, league)
        with field_tab:
            st.markdown("#### Projected tournament field")
            st.caption(
                "Selection scenario: 65% power percentile and 35% provisional SOR percentile "
                "when eligible (five rated D1 games); otherwise power only. "
                "Projected automatic bids are not earned conference championships."
            )
            view=st.radio(
                "Show teams",
                ["All 76","Projected automatic bids","Projected at-large bids","Opening Round"],
                horizontal=True,key="v138_filter"
            )
            shown=frame
            if view=="Projected automatic bids":
                shown=shown[shown["Bid type"].str.startswith("Projected automatic")]
            elif view=="Projected at-large bids":
                shown=shown[shown["Bid type"].str.startswith("Projected at-large")]
            elif view=="Opening Round":
                shown=shown[shown["Opening Round (proxy)"]]
            st.dataframe(
                shown[["Overall seed list","Team","Conference","Current power","SOR score",
                       "SOR games","Selection score","Selection basis","Bid type","Opening Round (proxy)"]],
                hide_index=True,use_container_width=True
            )
            st.caption(
                f"{int(frame['SOR eligible'].sum())} projected teams have eligible provisional SOR. "
                "Overall seed order is experimental, not NCAA regional seeding."
            )
            with st.expander("Model assumptions and limitations"):
                st.write(
                    "The field blends power with eligible provisional SOR and verified conference "
                    "labels; it does not yet model official NET, quadrant wins, eligibility changes, "
                    "committee selection rules, or actual conference tournament winners."
                )
        with advancement_tab:
            from tournament_advancement_v152 import render_advancement
            from tournament_ui_v140 import bracket_payload
            try:
                payload=bracket_payload(frame)
            except (KeyError,ValueError,TypeError) as exc:
                st.warning(f"Advancement scenario unavailable: {exc}")
            else:
                render_advancement(payload)
        with locations_tab:
            from tournament_locations_v145 import render_locations
            render_locations(frame, league)

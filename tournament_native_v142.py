"""Native Streamlit tournament bracket: real team buttons and four region views."""
from __future__ import annotations
import streamlit as st
from tournament_ui_v140 import bracket_payload
from tournament_full_v144 import render_full_overview

REGION_NAMES=("East","West","South","Midwest")


def render_native_bracket(field):
    try:
        data=bracket_payload(field)
    except (KeyError, ValueError, TypeError) as exc:
        st.warning(f"Bracket unavailable: {exc}")
        return
    st.subheader("National Tournament Bracket · Courtside Projection")
    st.caption("Hypothetical 2027 region assignments, not NCAA official placements. First-round percentages estimate neutral-court single-game win chances, not advancement probabilities.")
    selected=st.session_state.get("v142_bracket_team")
    if selected and selected in data["teams"]:
        team=data["teams"][selected]
        with st.container(border=True):
            st.markdown(f"#### {team['name']} · Team details")
            c1,c2,c3,c4=st.columns(4)
            c1.metric("Overall order",f"#{team['overall']}")
            c2.metric("Power rating",f"{team['power']:.1f}")
            c3.metric("SOR",f"{team['sor']:.2f}" if team["sor"] is not None else "Pending")
            c4.metric("Selection score",f"{team['selection']:.3f}")
            st.caption(f"{team['conference']} · {team['bid']} · {team['basis']}")
    else:
        st.info("Select a real team from the region bracket below to view its résumé here.")
    render_full_overview(data)
    st.markdown("### Expand a region · Clickable team details")
    names=[r["name"] for r in data["regions"]]
    region_name=st.radio("Region",names,horizontal=True,key="v142_region")
    region=next(r for r in data["regions"] if r["name"]==region_name)
    st.markdown(f"### {region_name} Region")
    st.caption("Select a team name to view its résumé. Matchups after the first round remain undecided.")
    st.markdown("""<style>
    .v142-game{border:1px solid #dbe3eb;background:#fff;border-radius:9px;padding:7px 10px;margin:8px 0}
    .v142-label{color:#718096;font-size:11px;font-weight:650}
    .v142-connector{height:28px;border-right:2px solid #afbecf;margin-right:50%;border-bottom:2px solid #afbecf}
    </style>""",unsafe_allow_html=True)
    rounds=st.columns([2.2,1.2,1.2,1.2],gap="small")
    labels=["Round of 64","Round of 32","Sweet 16","Elite Eight"]
    for idx,col in enumerate(rounds):
        with col:
            st.markdown(f"**{labels[idx]}**")
            if idx==0:
                for i,g in enumerate(region["games"]):
                    with st.container(border=True):
                        st.caption(f"Matchup {i+1}")
                        for side, p in ((g["a"],g["p"]),(g["b"],None if g["p"] is None else 1-g["p"])):
                            if side in data["teams"]:
                                label=f"{side}  ·  {p:.0%}" if p is not None else side
                                if st.button(label,key=f"v142_{region_name}_{i}_{side}",use_container_width=True):
                                    st.session_state["v142_bracket_team"]=side
                                    st.rerun()
                            else:
                                st.caption(side)
            else:
                count=8//(2**idx)
                for i in range(count):
                    with st.container(border=True):
                        st.caption(f"{labels[idx]} · Game {i+1}")
                        st.markdown("**Winner TBD**")
                        st.caption("Awaiting simulated results")
                    st.markdown('<div class="v142-connector"></div>',unsafe_allow_html=True)
    st.divider()
    with st.expander("Opening Round · All 12 projected matchups",expanded=False):
        for g in data["opening"]:
            c1,c2,c3=st.columns([2,1,2])
            a,b=g["a"],g["b"]
            with c1:
                if st.button(a,key=f"v142_open_{g['game']}_a",use_container_width=True):
                    st.session_state["v142_bracket_team"]=a
                    st.rerun()
            with c2:
                st.caption(f"{g['p']:.0%} / {1-g['p']:.0%}")
            with c3:
                if st.button(b,key=f"v142_open_{g['game']}_b",use_container_width=True):
                    st.session_state["v142_bracket_team"]=b
                    st.rerun()
    st.caption("Final Four and championship will be populated once an actual tournament simulation model is introduced.")

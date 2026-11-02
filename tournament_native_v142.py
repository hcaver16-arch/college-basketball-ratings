"""V197: bracket-first Tournament layout with native team interaction and right details."""
from __future__ import annotations
import html
import streamlit as st
from tournament_ui_v140 import bracket_payload
from tournament_full_v144 import render_full_overview
from tournament_region_labels_v147 import seeded_label, region_site, game_site_label
from tournament_first_weekend_v151 import assign_pod_sites, first_weekend_label

REGION_NAMES=("East","West","South","Midwest")


def _detail_panel(data, field, selected, league):
    """Compact résumé and conditional round chances, always in the right column."""
    st.markdown("#### Team details")
    if not selected or selected not in data["teams"]:
        st.info("Select a team in a region or the Opening Round to view its résumé.")
        return
    team = data["teams"][selected]
    matched=field[field["Team"].astype(str)==selected]
    tid=str(matched.iloc[0]["Team ID"]).strip() if not matched.empty else ""
    show_logo=st.session_state.get("courtside_logos_enabled",True)
    logo=(
        f'<img src="https://a.espncdn.com/i/teamlogos/ncaa/500/{tid}.png" '
        'alt="" loading="lazy" style="width:47px;height:47px;object-fit:contain"/>'
        if show_logo and tid.isdigit() else ""
    )
    st.markdown(
        '<div class="cs197-team-identity">' + logo
        + '<div><strong>' + html.escape(selected) + '</strong><small>'
        + html.escape(team["conference"]) + '</small></div></div>',
        unsafe_allow_html=True
    )
    c1,c2=st.columns(2,gap="small")
    with c1:
        st.metric("Overall order",f"#{team['overall']}")
        st.metric("Power rating",f"{team['power']:+.1f}")
    with c2:
        st.metric("SOR",f"{team['sor']:.2f}" if team["sor"] is not None else "Pending")
        st.metric("Selection score",f"{team['selection']:.3f}")
    st.caption(f"{team['bid']} · {team['basis']}")
    # Reuse the existing uncalibrated advancement calculation, not made-up winners.
    from tournament_advancement_v152 import advancement_probabilities
    try:
        chances=advancement_probabilities(data).get(selected,{})
    except (AssertionError,KeyError,ValueError,TypeError) as exc:
        chances={}
        st.caption(f"Advancement estimate unavailable: {exc}")
    if chances:
        st.markdown("**Tournament chances · Experimental**")
        for stage, caption in (
            ("Reach R32","Round of 32"),
            ("Reach Sweet 16","Sweet 16"),
            ("Reach Elite Eight","Elite Eight"),
            ("Reach Final Four","Final Four"),
            ("Win championship","Championship"),
        ):
            p=chances.get(stage)
            if p is not None:
                st.markdown(
                    '<div class="cs197-chance"><span>'+caption+'</span><strong>'
                    +f'{p:.1%}'+'</strong></div>',
                    unsafe_allow_html=True
                )
                st.progress(min(1.0,max(0.0,float(p))))
    if st.button("View full team profile →",key="cs197_team_profile",use_container_width=True):
        st.session_state["courtside_requested_team"]=selected
        if tid.isdigit():
            st.session_state["courtside_requested_team_id"]=tid
        st.session_state["courtside_page"]="Teams"
        st.rerun()
    st.caption("Projected selection and advancement probabilities are illustrative, not official NCAA predictions.")


def render_native_bracket(field, league="Men's"):
    try:
        data=bracket_payload(field)
    except (KeyError, ValueError, TypeError) as exc:
        st.warning(f"Bracket unavailable: {exc}")
        return
    st.markdown("""<style>
    .st-key-cs197_bracket_left {min-width:0}
    .st-key-cs197_bracket_details {border:1px solid #d6e2f3;border-top:4px solid #2858a4;
      border-radius:12px;background:#f9fbfe;padding:12px}
    .st-key-cs197_bracket_details [data-testid="stMetric"]{padding:8px!important}
    .cs197-team-identity{display:flex;align-items:center;gap:10px;margin:5px 0 13px}
    .cs197-team-identity strong{display:block;font-weight:800;font-size:.98rem;color:#1d3966;overflow-wrap:anywhere}
    .cs197-team-identity small{color:#6a7d98;font-size:.77rem}
    .cs197-chance{display:flex;justify-content:space-between;gap:8px;font-size:.79rem;margin-top:8px}
    .cs197-chance strong{color:#1d4c93}
    .st-key-cs197_bracket_left button{font-size:.77rem!important;overflow-wrap:anywhere;white-space:normal}
    .st-key-cs197_bracket_left [data-testid="stCaptionContainer"] p{font-size:.71rem}
    @media(max-width:700px){.st-key-cs197_bracket_details{margin-top:8px}}
    </style>""",unsafe_allow_html=True)
    assignments=assign_pod_sites(data) if league=="Men's" else None
    main_col,detail_col=st.columns([3.1,1.3],gap="medium")
    with main_col:
        with st.container(key="cs197_bracket_left"):
            view=st.segmented_control(
                "Bracket view",["By region","Full bracket"],
                default="By region",key="cs197_bracket_view"
            )
            if view=="Full bracket":
                render_full_overview(data, league, assignments)
                st.caption(
                    "The full bracket is a scrollable overview. Select By region to click a team "
                    "and inspect its résumé. Winners are not assumed."
                )
            else:
                names=[r["name"] for r in data["regions"]]
                region_name=st.radio("Region",names,horizontal=True,key="v142_region")
                region=next(r for r in data["regions"] if r["name"]==region_name)
                site,caveat=region_site(region_name,league)
                st.markdown(f"#### {region_name} Region")
                st.caption(f"Regional location: {site} · {caveat}")
                st.caption(
                    "Tap a team for the details panel. Percentages are illustrative "
                    "single-game win estimates, not guaranteed results."
                )
                rounds=st.columns([2.3,1.1,1.1,1.1],gap="small")
                labels=["Round of 64","Round of 32","Sweet 16","Elite Eight"]
                for idx,col in enumerate(rounds):
                    with col:
                        st.markdown(f"**{labels[idx]}**")
                        if idx==0:
                            for i,g in enumerate(region["games"]):
                                with st.container(border=True):
                                    st.caption(f"Matchup {i+1}")
                                    st.caption(
                                        first_weekend_label(assignments,region_name,0,i)
                                        if assignments is not None
                                        else game_site_label(0, region_name, league)
                                    )
                                    pairs=((g["a"],g["p"]),
                                           (g["b"],None if g["p"] is None else 1-g["p"]))
                                    for side_index,(side,p) in enumerate(pairs):
                                        if side in data["teams"]:
                                            seeded=seeded_label(side,i,side_index,data["teams"])
                                            label=f"{seeded} · {p:.0%}" if p is not None else seeded
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
                                    st.caption(
                                        first_weekend_label(assignments,region_name,idx,i)
                                        if assignments is not None and idx==1
                                        else game_site_label(idx, region_name, league)
                                    )
                                    st.markdown("**Winner TBD**")
                st.caption("Final Four and championship participants remain undecided in this hypothetical bracket.")
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
            if assignments is not None:
                st.caption(
                    "Projected first-weekend pod sites use a limited geographic scenario. "
                    "Unknown campus locations remain TBD; NCAA placements are not confirmed."
                )
    with detail_col:
        with st.container(key="cs197_bracket_details",border=True):
            selected=st.session_state.get("v142_bracket_team")
            if selected not in data["teams"]:
                selected=min(data["teams"],key=lambda name:data["teams"][name]["overall"])
            _detail_panel(data, field, selected, league)

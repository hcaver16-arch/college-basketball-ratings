"""Courtside V49 matchup scouting report. Presentation only; no model changes."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from net_quadrants import annotate_games, quadrant_records


def _number(x, fmt="+.1f"):
    try:
        n=float(x)
        return format(n, fmt) if pd.notna(n) else "—"
    except (TypeError, ValueError):
        return "—"


def _row(df, tid):
    if not isinstance(df,pd.DataFrame) or df.empty or "Team ID" not in df: return None
    m=df[df["Team ID"].astype(str)==str(tid)]
    return m.iloc[0] if not m.empty else None


def _cell(record, candidates, fmt=None):
    if record is None: return "—"
    for key in candidates:
        if key in record.index:
            v=record[key]
            if pd.notna(v):
                return _number(v,fmt) if fmt else str(v)
    return "—"


def _recent(frame, tid, n=5):
    if not isinstance(frame,pd.DataFrame) or frame.empty: return []
    subset=frame[(frame["Status"]=="Final") & ((frame["Home ID"].astype(str)==str(tid)) | (frame["Away ID"].astype(str)==str(tid)))].copy()
    if subset.empty: return []
    subset=subset.sort_values(["Date","Time (ET)"],ascending=False).head(n)
    results=[]
    for _,g in subset.iterrows():
        is_home=str(g["Home ID"])==str(tid)
        ours=pd.to_numeric(g.get("Home score") if is_home else g.get("Away score"),errors="coerce")
        other=pd.to_numeric(g.get("Away score") if is_home else g.get("Home score"),errors="coerce")
        if pd.isna(ours) or pd.isna(other): continue
        label="W" if ours>other else "L" if ours<other else "T"
        opponent=g["Away"] if is_home else g["Home"]
        results.append(f"{label} {int(ours)}–{int(other)} vs {opponent}" + (f" ({g['Date']})" if pd.notna(g.get('Date')) else ""))
    return results


def render_matchup(game, *, team_ratings, ratings, preliminary_ratings, sos_ratings, sor_ratings, games, net_ranks, net_status, verified_d1_ids, league, game_projection):
    """Render under an already open game header, using only existing verified app datasets."""
    away,home=str(game["Away"]),str(game["Home"])
    aid,hid=str(game["Away ID"]),str(game["Home ID"])
    is_d1=aid in verified_d1_ids and hid in verified_d1_ids
    away_rating=_row(team_ratings,aid)
    home_rating=_row(team_ratings,hid)
    projection=game_projection(game,ratings) if is_d1 else None
    if game.get("Status") in ("Live","Final"):
        a=pd.to_numeric(game.get("Away score"),errors="coerce")
        h=pd.to_numeric(game.get("Home score"),errors="coerce")
        if pd.notna(a) and pd.notna(h): st.markdown(f"### {away} {int(a)} — {home} {int(h)}")
    st.markdown("#### Model forecast")
    c1,c2,c3=st.columns(3)
    c1.metric("Projected spread",game.get("Model line","—"))
    c2.metric(f"{home} win probability", f"{projection[1]:.1f}%" if projection else "Unavailable")
    c3.metric("Roster scenario", (game.get("Experimental line","—") if str(game.get("Experimental line","—")) != str(game.get("Model line","—")) else "Same as baseline"))
    st.caption("Preliminary model estimates, not sportsbook odds. Roster effects are experimental; a matching line often means no usable roster adjustment.")
    if projection:
        a=ratings.get(aid); h=ratings.get(hid)
        if a is not None and h is not None:
            strength=float(h)-float(a)
            court=0.0 if str(game.get("Venue"))=="Neutral" else 3.0
            st.markdown("**Why the model favors this side**")
            x,y,z=st.columns(3)
            x.metric("Home − away team strength",f"{strength:+.1f} pts")
            y.metric("Home-court contribution",f"{court:+.1f} pts")
            z.metric("Estimated home margin",f"{strength+court:+.1f} pts")
            st.caption("The margin follows the existing rating-engine formula. A positive home margin favors the home team; neutral games receive no home-court adjustment.")

    st.markdown("#### Head-to-head team analytics")
    st.caption("Ratings, ranks and available schedule metrics; — means unavailable, not zero.")
    ar,hr=away_rating,home_rating
    so_a,so_h=_row(sos_ratings,aid),_row(sos_ratings,hid)
    sr_a,sr_h=_row(sor_ratings,aid),_row(sor_ratings,hid)
    rows=[
        ("Power rating",_cell(ar,["Current power"],"+.1f"),_cell(hr,["Current power"],"+.1f")),
        ("National power rank",_cell(ar,["Rank"]),_cell(hr,["Rank"])),
        ("Games played",_cell(ar,["Games played"]),_cell(hr,["Games played"])),
        ("SOS rank (provisional)",_cell(so_a,["SOS rank (provisional)"]),_cell(so_h,["SOS rank (provisional)"])),
        ("SOS (loaded schedule)",_cell(so_a,["Full SOS"],"+.1f"),_cell(so_h,["Full SOS"],"+.1f")),
        ("SOR rank (provisional)",_cell(sr_a,["SOR rank (provisional)"]),_cell(sr_h,["SOR rank (provisional)"])),
        ("Record (loaded games)",_cell(sr_a,["Wins"])+"–"+_cell(sr_a,["Losses"]),_cell(sr_h,["Wins"])+"–"+_cell(sr_h,["Losses"])),
    ]
    st.dataframe(pd.DataFrame(rows,columns=["Metric",away,home]),hide_index=True,use_container_width=True)
    st.caption("SOS/SOR may cover only the currently loaded schedule. Provisional ranks must not be interpreted as official NCAA rankings.")

    with st.expander("Recent results — last five loaded final games",expanded=True):
        a,h=st.columns(2)
        for col,name,tid in ((a,away,aid),(h,home,hid)):
            with col:
                st.markdown(f"**{name}**")
                results=_recent(games,tid)
                if results:
                    for result in results: st.write(result)
                else: st.caption("No completed games available in the loaded period.")
    st.markdown("#### NET quadrants and tournament résumé")
    st.caption(net_status)
    q1,q2=st.columns(2)
    with q1:
        st.metric(f"{away} quadrant",game.get("Away quadrant","NET unavailable"))
        st.caption("Opponent NET: " + (_number(game.get("Away opponent NET"),".0f") if pd.notna(game.get("Away opponent NET")) else "Unavailable"))
    with q2:
        st.metric(f"{home} quadrant",game.get("Home quadrant","NET unavailable"))
        st.caption("Opponent NET: " + (_number(game.get("Home opponent NET"),".0f") if pd.notna(game.get("Home opponent NET")) else "Unavailable"))
    if net_ranks:
        ann=annotate_games(games,net_ranks,verified_d1_ids,league)
        away_rec=quadrant_records(ann,aid);home_rec=quadrant_records(ann,hid)
        st.dataframe(pd.DataFrame([{"Quadrant":q,away:f"{away_rec[q][0]}–{away_rec[q][1]}",home:f"{home_rec[q][0]}–{home_rec[q][1]}"} for q in ("Q1","Q2","Q3","Q4")]),hide_index=True,use_container_width=True)
        st.caption("These records reflect final games in the loaded date window, classified with the latest loaded NET snapshot; not necessarily complete official season records.")
    else:
        st.info("Official NET data not yet available. Quadrant labels and records will appear once a current-season verified NET snapshot is loaded.")
    with st.expander("Roster adjustment and methodology",expanded=False):
        st.write("Roster input status:",str(game.get("Roster input status","Unavailable")))
        a_pr=_row(preliminary_ratings,aid);h_pr=_row(preliminary_ratings,hid)
        st.dataframe(pd.DataFrame([
            {"Team":away,"Baseline":_cell(a_pr,["Current power"],"+.2f"),"Roster adjustment":_cell(a_pr,["Roster adjustment"],"+.2f"),"Experimental rating":_cell(a_pr,["Experimental power"],"+.2f"),"Data status":_cell(a_pr,["Roster data status"])},
            {"Team":home,"Baseline":_cell(h_pr,["Current power"],"+.2f"),"Roster adjustment":_cell(h_pr,["Roster adjustment"],"+.2f"),"Experimental rating":_cell(h_pr,["Experimental power"],"+.2f"),"Data status":_cell(h_pr,["Roster data status"])},
        ]),hide_index=True,use_container_width=True)
        st.caption("The returning-production adjustment is preliminary and untrained; missing evidence falls back to zero adjustment. No transfer impact is invented.")
    url=game.get("Game URL")
    if isinstance(url,str) and url.startswith("https://"): st.link_button("Open game source",url)

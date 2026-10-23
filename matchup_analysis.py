"""Courtside V49 matchup scouting report. Presentation only; no model changes."""
from __future__ import annotations
import pandas as pd
from html import escape
import streamlit as st
from net_quadrants import annotate_games, quadrant_records
from team_identity import team_identity


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


def _card(label, value, sub=""):
    """Short responsive stat card. Escape all source-derived strings."""
    st.markdown(
        '<div class="cs-kpi">'
        f'<div class="cs-kpi-label">{escape(str(label))}</div>'
        f'<div class="cs-kpi-value">{escape(str(value))}</div>'
        + (f'<div class="cs-kpi-sub">{escape(str(sub))}</div>' if sub else '')
        + '</div>', unsafe_allow_html=True
    )


# Exact exceptions for schools whose conventional short name differs from the
# first words of their ESPN display name.
_SCHOOL_ALIASES = {
    "Connecticut": "UConn",
    "Connecticut Huskies": "UConn",
    "Southern California Trojans": "USC",
    "USC Trojans": "USC",
    "Brigham Young Cougars": "BYU",
    "BYU Cougars": "BYU",
    "UCLA Bruins": "UCLA",
    "UNLV Rebels": "UNLV",
    "UCF Knights": "UCF",
    "LSU Tigers": "LSU",
    "SMU Mustangs": "SMU",
    "TCU Horned Frogs": "TCU",
    "UTEP Miners": "UTEP",
    "UTSA Roadrunners": "UTSA",
    "VCU Rams": "VCU",
    "Ole Miss Rebels": "Ole Miss",
    "Miami Hurricanes": "Miami",
    "Miami (OH) RedHawks": "Miami (OH)",
    "Saint Mary's Gaels": "Saint Mary's",
}

# Only remove identifiable full mascot suffixes. No generic split on spaces:
# multi-word schools like North Carolina Central must stay intact.
_MASCOTS = (
    "Fighting Irish", "Red Raiders", "Golden Eagles", "Blue Devils",
    "Tar Heels", "Lady Volunteers", "Demon Deacons", "Golden Gophers",
    "Crimson Tide", "Horned Frogs", "Fighting Illini", "Mountaineers",
    "Lady Raiders", "Red Wolves", "Golden Bears", "Mean Green",
    "Yellow Jackets", "Rainbow Warriors", "Rainbow Wahine", "Ragin' Cajuns",
    "Lumberjacks", "Fighting Camels", "Red Storm", "Black Bears",
    "Wildcats", "Panthers", "Bulldogs", "Huskies", "Spartans",
    "Tigers", "Bears", "Eagles", "Cougars", "Hurricanes",
    "Wolverines", "Cyclones", "Jayhawks", "Bruins", "Knights",
    "Rebels", "Sooners", "Longhorns", "Cardinals", "Razorbacks",
    "Buckeyes", "Badgers", "Boilermakers", "Seminoles", "Gators",
    "Volunteers", "Terrapins", "Wolfpack", "Gaels", "Rams",
    "Flames", "Pirates", "Owls", "Ducks", "Hokies", "Mustangs",
    "Aggies", "Bobcats", "Broncos", "Bison", "Trojans", "Bulls",
    "Lions", "Hawks", "Jaguars", "Dukes", "Friars", "Pilots",
    "Gamecocks", "Bearcats", "Miners", "Roadrunners", "Raiders",
    "Explorers", "Musketeers", "Billikens", "Bonnies", "Quakers",
    "Beavers", "Hoyas", "Aztecs", "Shockers", "Zips", "Antelopes",
    "49ers", "Monarchs", "Peacocks", "Highlanders", "Keydets",
    "Paladins", "Governors", "Ramblers", "Rattlers", "Ospreys",
    "Catamounts", "Dolphins", "Terriers", "Titans", "Penguins",
    "Mocs", "Chanticleers", "Retrievers", "Seawolves", "Lancers",
)


def short_school_name(full_name):
    """Readable school name for a compact prediction card, not a team ID."""
    name = str(full_name or "").strip()
    if not name:
        return "Team"
    if name in _SCHOOL_ALIASES:
        return _SCHOOL_ALIASES[name]
    for mascot in sorted(_MASCOTS, key=len, reverse=True):
        suffix = " " + mascot
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[:-len(suffix)]
    return name  # Unknown school: do not make up an abbreviation.


def _compact_line(game, projection):
    """School-based spread label using the actual model margin and game teams."""
    if projection is not None:
        try:
            home_margin = float(projection[0])
            if pd.notna(home_margin):
                if abs(home_margin) < 0.05:
                    return "Pick 'em"
                favored_name = game.get("Home") if home_margin > 0 else game.get("Away")
                return f"{short_school_name(favored_name)} -{abs(home_margin):.1f}"
        except (TypeError, ValueError, IndexError):
            pass
    return str(game.get("Model line") or "Unavailable")


def render_matchup(game, *, team_ratings, ratings, preliminary_ratings, sos_ratings, sor_ratings, games, net_ranks, net_status, verified_d1_ids, league, game_projection, away_record=None, home_record=None, record_coverage_ok=True):
    """Render under an already open game header, using only existing verified app datasets."""
    st.markdown("""<style>
    .cs-kpi {background:#fff;border:1px solid #e2e8f0;border-radius:13px;padding:15px 16px;min-height:116px;box-sizing:border-box}
    .cs-kpi-label {font-size:.79rem;color:#64748b;font-weight:650;line-height:1.3;margin-bottom:9px}
    .cs-kpi-value {color:#1d2c40!important;font-size:clamp(1.05rem,2vw,1.65rem)!important;font-weight:750;line-height:1.2!important;white-space:normal!important;overflow:visible!important;text-overflow:clip!important;overflow-wrap:anywhere!important;word-break:break-word!important}
    .cs-kpi-sub {font-size:.75rem;color:#718096;margin-top:8px;overflow-wrap:anywhere}
    .cs-comparison {border:1px solid #e2e8f0;background:#fff;border-radius:14px;overflow:hidden;margin:.6rem 0}
    .cs-comp-row {display:grid;grid-template-columns:minmax(0,1fr) minmax(110px,.85fr) minmax(0,1fr);gap:8px;align-items:center;padding:12px 16px;border-top:1px solid #edf1f6}
    .cs-comp-row:first-child {border-top:0;background:#f8fafc}
    .cs-comp-name {font-size:.82rem;color:#64748b;text-align:center;overflow-wrap:anywhere}
    .cs-comp-val {font-weight:650;color:#1d2c40;font-size:.92rem;overflow-wrap:anywhere}
    .cs-comp-right {text-align:right}
    @media(max-width:600px) {.cs-comp-row {grid-template-columns:minmax(0,1fr) 95px minmax(0,1fr);padding:10px 8px;gap:4px}.cs-comp-name{font-size:.7rem}.cs-comp-val{font-size:.82rem}}
    </style>""",unsafe_allow_html=True)
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
    # Private/personal site: opt in to third-party logos, with initials as safe default.
    external_logos = st.toggle(
        "Show external school logos (ESPN-hosted)", value=False,
        key="courtside_show_external_team_logos",
        help="School logos may be protected by trademark/copyright. An image URL does not grant permission to reuse it."
    )
    with st.container(border=True):
        a_col, vs_col, h_col = st.columns([4, 1, 4], vertical_alignment="center")
        team_identity(a_col, away, aid, league, external_logos=external_logos)
        with a_col:
            st.markdown(f"**{away_record}** · Pregame record" if away_record is not None else "Record unavailable")
        with vs_col:
            st.markdown("### at" if str(game.get("Venue")) != "Neutral" else "### vs")
        team_identity(h_col, home, hid, league, external_logos=external_logos)
        with h_col:
            st.markdown(f"**{home_record}** · Pregame record" if home_record is not None else "Record unavailable")
        if external_logos:
            st.caption("Logos are externally hosted and belong to their respective rights holders; Courtside is not affiliated with or endorsed by these schools.")
    if not record_coverage_ok:
        st.caption("Records may be incomplete because some season schedule dates could not be loaded.")
    st.markdown("#### Model forecast")
    c1,c2,c3=st.columns(3)
    with c1:
        _card("Projected spread", _compact_line(game,projection), "Preliminary projection, not betting odds")
    with c2:
        _card("Home win probability", f"{projection[1]:.1f}%" if projection else "Unavailable", home)
    with c3:
        different = str(game.get("Experimental line","—")) != str(game.get("Model line","—"))
        _card("Roster scenario", "Adjustment applied" if different else "Same as baseline", str(game.get("Experimental line","—")) if different else "No difference in displayed line")
    st.caption("Preliminary model estimates, not sportsbook odds. Roster effects are experimental; a matching line often means no usable roster adjustment.")
    if projection:
        a=ratings.get(aid); h=ratings.get(hid)
        if a is not None and h is not None:
            strength=float(h)-float(a)
            court=0.0 if str(game.get("Venue"))=="Neutral" else 3.0
            st.markdown("**Why the model favors this side**")
            x,y,z=st.columns(3)
            with x: _card("Home − away strength",f"{strength:+.1f} pts")
            with y: _card("Home-court adjustment",f"{court:+.1f} pts")
            with z: _card("Estimated home margin",f"{strength+court:+.1f} pts")
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
    # Public-facing comparison uses light responsive rows rather than a dense data grid.
    comp = ['<div class="cs-comparison">',
            '<div class="cs-comp-row"><div class="cs-comp-val">'+escape(away)+'</div><div class="cs-comp-name">METRIC</div><div class="cs-comp-val cs-comp-right">'+escape(home)+'</div></div>']
    for label, aval, hval in rows:
        if aval == '—' and hval == '—':
            continue  # Do not fill the preseason report with empty metrics.
        if label == 'Record (loaded games)' and aval == '—–—' and hval == '—–—':
            continue
        comp.append('<div class="cs-comp-row"><div class="cs-comp-val">'+escape(str(aval))+'</div><div class="cs-comp-name">'+escape(str(label))+'</div><div class="cs-comp-val cs-comp-right">'+escape(str(hval))+'</div></div>')
    comp.append('</div>')
    st.markdown(''.join(comp),unsafe_allow_html=True)
    st.caption("SOS/SOR may cover only the currently loaded schedule. Provisional ranks must not be interpreted as official NCAA rankings.")

    has_recent = bool(_recent(games,aid) or _recent(games,hid))
    with st.expander("Recent results — last five loaded final games" + ("" if has_recent else " (not yet available)"),expanded=False):
        a,h=st.columns(2)
        for col,name,tid in ((a,away,aid),(h,home,hid)):
            with col:
                st.markdown(f"**{name}**")
                results=_recent(games,tid)
                if results:
                    for result in results: st.write(result)
                else: st.caption("No completed games available in the loaded period.")
    if net_ranks:
        st.markdown("#### NET quadrants and tournament résumé")
        st.caption(net_status)
        q1,q2=st.columns(2)
        with q1:
            _card(f"{away} quadrant",game.get("Away quadrant","NET unavailable"), "Opponent NET: " + (_number(game.get("Away opponent NET"),".0f") if pd.notna(game.get("Away opponent NET")) else "Unavailable"))
        with q2:
            _card(f"{home} quadrant",game.get("Home quadrant","NET unavailable"), "Opponent NET: " + (_number(game.get("Home opponent NET"),".0f") if pd.notna(game.get("Home opponent NET")) else "Unavailable"))
        with st.expander("Quadrant win–loss records",expanded=False):
            ann=annotate_games(games,net_ranks,verified_d1_ids,league)
            away_rec=quadrant_records(ann,aid);home_rec=quadrant_records(ann,hid)
            st.dataframe(pd.DataFrame([{"Quadrant":q,away:f"{away_rec[q][0]}–{away_rec[q][1]}",home:f"{home_rec[q][0]}–{home_rec[q][1]}"} for q in ("Q1","Q2","Q3","Q4")]),hide_index=True,use_container_width=True)
            st.caption("Records reflect loaded completed games classified with the latest available NET snapshot, not necessarily the full official season.")
    else:
        with st.expander("NET quadrants — awaiting official current-season rankings", expanded=False):
            st.caption(net_status)
            st.info("Official NET data isn't available yet. Quadrant labels and records will appear once a verified current-season snapshot is loaded.")
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

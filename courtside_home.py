"""Light-themed Courtside home components. No new data source or model calculation."""
from __future__ import annotations
import html
import pandas as pd
import streamlit as st

PALETTE = {"Texas Tech":"#C6283A","Kansas":"#0051BA","Duke":"#003087",
           "North Carolina":"#4B9CD3","Houston":"#C8102E","Baylor":"#154734",
           "Arizona":"#AB0520","UConn":"#000E2F","Purdue":"#CEB888"}

def color_for(name):
    name = str(name)
    return next((color for school, color in PALETTE.items() if school.lower() in name.lower()), '#52677F')

def style():
    st.markdown('''<style>
    .stApp { background:#F5F6F8; color:#19283D; }
    [data-testid="stHeader"] { background:#F5F6F8; }
    [data-testid="stSidebar"] {background:#FFFFFF;}
    h1,h2,h3 { color:#19283D;letter-spacing:-.025em; }
    /* Navigation uses native Streamlit buttons; do not override button labels with the old dark-theme text. */
    div.stButton>button { border-radius:9px; font-weight:600; min-height:40px; }
    div.stButton>button[kind="secondary"] {
        background:#FFFFFF; border:1px solid #DCE3EC; color:#26364B;
    }
    div.stButton>button[kind="secondary"] p { color:#26364B !important; }
    div.stButton>button[kind="primary"] {
        background:#23354B; border:1px solid #23354B; color:#FFFFFF;
    }
    div.stButton>button[kind="primary"] p { color:#FFFFFF !important; }
    div.stButton>button:hover {border-color:#5F7895;}
    /* Ensure core text is readable even if the deployment's Streamlit theme defaults to dark. */
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {color:#64748B !important;}
    [data-testid="stMetricLabel"] p {color:#526174 !important;}
    [data-testid="stMetricValue"] {color:#19283D !important;}
    [data-testid="stMetricValue"] * {color:#19283D !important;}
    div[data-testid="stMetric"] {background:#FFFFFF;border:1px solid #E4E9F0;border-radius:12px;padding:12px;}
    div[data-testid="stVerticalBlockBorderWrapper"] {border-radius:13px;}
    /* Homepage ranking and highlight sections, deliberately independent of Streamlit dataframe dark mode. */
    .court-section-head {display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:20px 0 10px;}
    .court-section-head h3 {font-size:1.25rem;font-weight:750;margin:0;color:#19283D;}
    .court-section-head>span {font-size:.78rem;color:#718096;}
    .court-rank-card {overflow:hidden;background:#FFFFFF;border:1px solid #E3E8EF;border-radius:14px;margin-bottom:9px;}
    .court-rank-row {display:grid;grid-template-columns:44px minmax(0,1fr) 100px;align-items:center;gap:10px;min-height:54px;padding:10px 18px;border-bottom:1px solid #EEF1F5;color:#26364B;}
    .court-rank-row:last-child {border-bottom:0;}
    .court-rank-num {font-weight:750;color:#65758A;font-size:.9rem;}
    .court-rank-team {display:flex;align-items:center;gap:11px;font-weight:650;min-width:0;}
    .court-team-dot {display:inline-block;flex:0 0 9px;width:9px;height:9px;border-radius:50%;}
    .court-rank-score {text-align:right;font-variant-numeric:tabular-nums;font-weight:750;}
    .court-highlights {display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-bottom:16px;}
    .court-highlight-card {background:#FFFFFF;border:1px solid #E3E8EF;border-radius:13px;padding:16px;min-width:0;}
    .court-highlight-label {font-size:.68rem;color:#64748B;font-weight:750;letter-spacing:.06em;}
    .court-highlight-team {color:#26364B;font-size:.96rem;font-weight:700;margin:9px 0;}
    .court-highlight-team span {color:#8694A4;font-weight:400;}
    .court-highlight-margin {color:#63748A;font-size:.79rem;}
    .court-highlight-margin strong {color:#23354B;}
    @media (max-width:600px) {.court-rank-row{grid-template-columns:26px minmax(0,1fr) 72px;padding:10px 12px;gap:7px;}.court-section-head>span{display:none;}}


    /* V157: compact dashboard-like homepage cards and responsive two-column layout. */
    .cs157-home-banner {padding:15px 22px !important;margin-bottom:9px !important;}
    .cs157-home-banner h2 {font-size:1.55rem !important;margin:3px 0 !important;}
    .cs157-home-banner p {font-size:.82rem !important;}
    .cs157-home-banner .cs153-chips {margin-top:8px !important;}
    .cs157-home-banner .cs153-chip {font-size:10px !important;padding:3px 9px !important;}
    .court-rank-row {min-height:43px;padding:7px 12px;}
    .court-highlight-card {padding:10px !important;}
    .court-highlights {grid-template-columns:1fr;gap:7px;}
    @media (max-width:700px) {.cs157-home-banner {padding:13px 14px !important;}.cs157-home-banner h2 {font-size:1.35rem !important;}}
    /* V160: more readable compact featured matchup. */
    .cs160-feature-title {font-size:1.14rem;font-weight:750;color:#17345f;margin:7px 0 5px;}
    .cs160-matchup {display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);align-items:center;gap:8px;margin-bottom:8px;}
    .cs160-team {min-width:0;padding:4px 8px;font-size:clamp(.8rem,1.1vw,1rem);font-weight:750;color:#193253;line-height:1.3;overflow-wrap:anywhere;}
    .cs160-away {text-align:right;}
    .cs160-tip {font-size:.7rem;color:#637994;text-align:center;max-width:110px;}
    .cs160-predictions {display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:6px;}
    .cs160-stat {min-width:0;background:#f6fbff;border:1px solid #d5e5f6;border-radius:10px;padding:8px 10px;}
    .cs160-stat span {display:block;color:#5c718c;font-size:.63rem;font-weight:650;letter-spacing:.02em;margin-bottom:3px;overflow-wrap:anywhere;}
    .cs160-stat strong {display:block;color:#153560;font-size:1.03rem;line-height:1.25;overflow-wrap:anywhere;}
    @media(max-width:700px){.cs160-tip{max-width:65px;}.cs160-stat strong{font-size:.9rem;}}
    /* V161: restore a restrained branded header without hiding the games. */
    .cs161-home-header {background:linear-gradient(110deg,#12306a,#1b469d 72%,#1e78b5);border-radius:12px;padding:12px 18px;color:#fff;margin:0 0 7px;box-shadow:0 3px 10px rgba(20,50,95,.08);border:1px solid rgba(255,255,255,.08);}
    .cs161-eyebrow {color:#c7daf8;font-size:.61rem;font-weight:800;letter-spacing:.12em;}
    .cs161-header-title {font-size:1.35rem;font-weight:800;letter-spacing:-.025em;line-height:1.28;margin:2px 0;}
    .cs161-header-sub {font-size:.75rem;color:#e6f0ff;}
    .cs160-feature-title {margin:0 0 5px !important;}
    .court-section-head {margin:0 0 10px !important;min-height:28px;align-items:center;}
    .court-section-head h3 {font-size:1.12rem !important;}
    @media(max-width:700px){.cs161-home-header{padding:10px 12px;}.cs161-header-title{font-size:1.16rem;}}
    </style>''',unsafe_allow_html=True)

def featured_choice(upcoming, ratings, d1_ids):
    """Prefer D1 games with two rated teams; strong teams and close projections."""
    if upcoming.empty:return None
    shortlist=upcoming[upcoming['Home ID'].astype(str).isin(d1_ids) & upcoming['Away ID'].astype(str).isin(d1_ids)].copy()
    if shortlist.empty:return None
    shortlist=shortlist[shortlist['Home ID'].astype(str).isin(ratings) & shortlist['Away ID'].astype(str).isin(ratings)].copy()
    if shortlist.empty:return None
    def value(row):
        h,a=ratings[str(row['Home ID'])],ratings[str(row['Away ID'])]
        margin=h-a+(0 if row['Venue']=='Neutral' else 3)
        return max(h,a)*0.4+min(h,a)*0.2-abs(margin)*0.45
    shortlist['_interesting']=shortlist.apply(value,axis=1)
    return shortlist.sort_values('_interesting',ascending=False).iloc[0]

def render_home(games, ratings, team_ratings, d1_ids, league, window):
    time_zone = st.session_state.get("courtside_timezone", "Central")
    st.markdown("""<div class="cs161-home-header">
      <div><span class="cs161-eyebrow">COURTSIDE · COLLEGE BASKETBALL ANALYTICS</span>
      <div class="cs161-header-title">Every game. A clearer edge.</div>
      <div class="cs161-header-sub">Matchups · Power ratings · Tournament outlook</div></div>
    </div>""", unsafe_allow_html=True)
    st.markdown('### Today’s games')
    st.caption(f"{league} Division I · {window} · Tipoff times in {time_zone}")
    today=pd.Timestamp.now(tz='America/New_York').date()
    visible=games[games['Date'].eq(str(today))].copy()
    # Before the season, offer next available games instead of a fake 'today' list.
    if visible.empty:
        remaining=games[games['Status'].eq('Scheduled')].copy()
        remaining=remaining[remaining['Date']>=str(today)]
        if not remaining.empty:
            target=remaining['Date'].min()
            visible=remaining[remaining['Date'].eq(target)].copy()
            st.info(f"No games are listed today in the selected window. Showing the next scheduled date: {target}.")
        else:st.info('No games are listed for today in the selected schedule window.')
    rated_count=len(team_ratings) if isinstance(team_ratings,pd.DataFrame) else 0
    d1_visible=visible[visible['Home ID'].astype(str).isin(d1_ids)&visible['Away ID'].astype(str).isin(d1_ids)]
    st.caption(f"{len(visible):,} games · {len(d1_visible):,} D1 matchups · {rated_count:,} teams rated")
    if visible.empty:return
    home_main, home_side = st.columns([1.65, 1], gap='large')
    with home_main:
        scheduled=visible[visible['Status']=='Scheduled']
        featured=featured_choice(scheduled,ratings,d1_ids)
        if featured is not None:
            h,a=str(featured['Home']),str(featured['Away'])
            hid,aid=str(featured['Home ID']),str(featured['Away ID'])
            home_color,away_color=color_for(h),color_for(a)
            margin=ratings[hid]-ratings[aid]+(0 if featured['Venue']=='Neutral' else 3)
            from math import erf,sqrt
            chance=.5*(1+erf(margin/(11*sqrt(2))))
            favorite=h if margin>=0 else a
            st.markdown('<div class="cs160-feature-title">Featured matchup</div>', unsafe_allow_html=True)
            with st.container(border=True):
                st.markdown(f'''<div class="cs160-matchup">
                  <div class="cs160-team" style="border-left:4px solid {home_color}">{html.escape(h)}</div>
                  <div class="cs160-tip">VS · {html.escape(str(featured.get('Display time',featured['Time (ET)'])))}</div>
                  <div class="cs160-team cs160-away" style="border-right:4px solid {away_color}">{html.escape(a)}</div>
                </div>''',unsafe_allow_html=True)
                st.markdown('<div class="cs160-predictions">'
                    f'<div class="cs160-stat"><span>PROJECTED SPREAD</span><strong>{html.escape(favorite)} -{abs(margin):.1f}</strong></div>'
                    f'<div class="cs160-stat"><span>{html.escape(h)} WIN PROBABILITY</span><strong>{chance:.0%}</strong></div>'
                    '</div>', unsafe_allow_html=True)
                st.progress(float(max(0,min(1,chance))))
                st.caption('Experimental model prediction · Not a sportsbook line')
                if st.button('View featured game details →',key='courtside_feature_details'):
                    st.session_state['courtside_selected_game']=str(featured['Game ID'])
                    st.session_state['courtside_requested_page']='Games'
                    st.rerun()
        else:
            st.caption('A featured matchup will appear when both D1 opponents have published ratings.')
        st.markdown('#### All games')
        st.caption('Scrollable matchup list · Choose a game to open its details')
        with st.container(height=310,border=True):
            for ix, row in visible.reset_index(drop=True).iterrows():
                home,away=str(row['Home']),str(row['Away'])
                h_id,a_id=str(row['Home ID']),str(row['Away ID'])
                d1=h_id in d1_ids and a_id in d1_ids
                proj=None
                if d1 and h_id in ratings and a_id in ratings and row['Status']=='Scheduled':
                    m=ratings[h_id]-ratings[a_id]+(0 if row['Venue']=='Neutral' else 3)
                    proj=f"{home if m>=0 else away} -{abs(m):.1f}"
                color=color_for(home)
                x,y=st.columns([4,1.5],vertical_alignment='center')
                with x:
                    st.markdown(f'<div style="border-left:4px solid {color};padding-left:11px"><b>{html.escape(away)} @ {html.escape(home)}</b><br><span style="color:#64748B;font-size:12px">{html.escape(str(row.get("Display time",row["Time (ET)"])))}  · {html.escape(str(row["Status"]))} · {"D1 vs D1" if d1 else "Other matchup"}</span><br><span style="font-size:13px">{"Model: "+html.escape(proj) if proj else "No D1 model line"}</span></div>',unsafe_allow_html=True)
                with y:
                    if st.button('Details →',key=f'court_game_{row["Game ID"]}_{ix}',use_container_width=True):
                        st.session_state['courtside_selected_game']=str(row['Game ID'])
                        st.session_state['courtside_requested_page']='Games'
                        st.rerun()
                st.divider()
    with home_side:
        # Integrated light-theme rankings card: native st.dataframe rendered dark on some deployments.
        if isinstance(team_ratings,pd.DataFrame) and {'Team','Current power'}.issubset(team_ratings.columns) and not team_ratings.empty:
            top=team_ratings.sort_values('Current power',ascending=False).head(5).copy()
            rows=[]
            for rank,(_,team) in enumerate(top.iterrows(), start=1):
                name=str(team['Team'])
                rating=float(team['Current power'])
                school_color=color_for(name)
                rows.append(
                    f'<div class="court-rank-row">'
                    f'<span class="court-rank-num">{rank}</span>'
                    f'<span class="court-rank-team"><span class="court-team-dot" style="background:{school_color}"></span>{html.escape(name)}</span>'
                    f'<strong class="court-rank-score">{rating:+.2f}</strong>'
                    f'</div>'
                )
            st.markdown('<div class="court-section-head"><h3>Power rankings</h3><span>Top 5 teams</span></div>'
                        +'<div class="court-rank-card">'+''.join(rows)+'</div>',unsafe_allow_html=True)
            if st.button('View full rankings →',key='courtside_rankings'):
                st.session_state['courtside_requested_page']='Rankings';st.rerun()
        else:
            st.markdown('#### Power rankings')
            st.info('Power rankings will appear when saved ratings are available.')
        st.markdown('<div class="court-section-head"><h3>Matchup highlights</h3><span>Closest projected games</span></div>',unsafe_allow_html=True)
        if not d1_visible.empty:
            rated=d1_visible[d1_visible['Home ID'].astype(str).isin(ratings)&d1_visible['Away ID'].astype(str).isin(ratings)]
            scores=[]
            for _,g in rated[rated['Status']=='Scheduled'].iterrows():
                m=ratings[str(g['Home ID'])]-ratings[str(g['Away ID'])]+(0 if g['Venue']=='Neutral' else 3)
                scores.append((abs(m),str(g['Away']),str(g['Home'])))
            if scores:
                parts=[]
                for closeness,away,home in sorted(scores)[:3]:
                    parts.append('<div class="court-highlight-card">'
                                 '<div class="court-highlight-label">CLOSE MATCHUP</div>'
                                 f'<div class="court-highlight-team">{html.escape(away)} <span>at</span> {html.escape(home)}</div>'
                                 f'<div class="court-highlight-margin">Projected margin <strong>{closeness:.1f} pts</strong></div>'
                                 '</div>')
                st.markdown('<div class="court-highlights">'+''.join(parts)+'</div>',unsafe_allow_html=True)
            else:st.caption('Highlights will appear as D1 games are scheduled and rated.')
        else:st.caption('No verified D1 matchups are available on the displayed date.')

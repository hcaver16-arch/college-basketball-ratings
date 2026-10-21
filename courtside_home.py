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
    div.stButton>button { border-radius:9px; }
    div[data-testid="stMetric"] {background:#FFFFFF;border:1px solid #E4E9F0;border-radius:12px;padding:12px;}
    div[data-testid="stVerticalBlockBorderWrapper"] {border-radius:13px;}
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
    st.markdown('### Today’s matchups & highlights')
    st.caption(f"{league} Division I · Loaded schedule: {window}. Times shown in Eastern Time.")
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
    c1,c2,c3=st.columns(3)
    c1.metric('Games shown',f'{len(visible):,}')
    c2.metric('D1 vs D1 games',f'{len(d1_visible):,}')
    c3.metric('Teams rated',f'{rated_count:,}')
    if visible.empty:return
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
        st.markdown('#### Featured matchup')
        with st.container(border=True):
            st.markdown(f'''<div style="display:flex;justify-content:space-between;align-items:center;gap:14px;padding:6px 0 16px">
            <div style="border-left:5px solid {home_color};padding-left:12px;font-weight:700;font-size:21px">{html.escape(h)}</div>
            <div style="color:#738196;font-size:13px">VS<br>{html.escape(str(featured['Time (ET)']))} ET</div>
            <div style="border-right:5px solid {away_color};padding-right:12px;font-weight:700;font-size:21px;text-align:right">{html.escape(a)}</div>
            </div>''',unsafe_allow_html=True)
            f1,f2=st.columns(2)
            f1.metric('Model projected spread',f'{favorite} -{abs(margin):.1f}')
            f2.metric(f'{h} win probability',f'{chance:.0%}')
            st.progress(float(max(0,min(1,chance))),text='Estimated home-team win probability')
            st.caption('Experimental model estimate, not a sportsbook betting line.')
            if st.button('View featured game details →',key='courtside_feature_details'):
                st.session_state['courtside_selected_game']=str(featured['Game ID'])
                st.session_state['courtside_requested_page']='Games'
                st.rerun()
    else:
        st.caption('A featured matchup will appear when both D1 opponents have published ratings.')
    st.markdown('#### All games')
    st.caption('Scrollable matchup list · Choose a game to open its details')
    with st.container(height=440,border=True):
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
                st.markdown(f'<div style="border-left:4px solid {color};padding-left:11px"><b>{html.escape(away)} @ {html.escape(home)}</b><br><span style="color:#64748B;font-size:12px">{html.escape(str(row["Time (ET)"]))} ET · {html.escape(str(row["Status"]))} · {"D1 vs D1" if d1 else "Other matchup"}</span><br><span style="font-size:13px">{"Model: "+html.escape(proj) if proj else "No D1 model line"}</span></div>',unsafe_allow_html=True)
            with y:
                if st.button('Details →',key=f'court_game_{row["Game ID"]}_{ix}',use_container_width=True):
                    st.session_state['courtside_selected_game']=str(row['Game ID'])
                    st.session_state['courtside_requested_page']='Games'
                    st.rerun()
            st.divider()
    st.markdown('#### Power rankings')
    if isinstance(team_ratings,pd.DataFrame) and {'Team','Current power'}.issubset(team_ratings.columns) and not team_ratings.empty:
        top=team_ratings.sort_values('Current power',ascending=False).head(5).copy()
        top.insert(0,'#',range(1,len(top)+1))
        st.dataframe(top[['#','Team','Current power']].rename(columns={'Current power':'Power rating'}),hide_index=True,use_container_width=True)
        if st.button('View full rankings →',key='courtside_rankings'):
            st.session_state['courtside_requested_page']='Rankings';st.rerun()
    else:st.info('Power rankings will appear when saved ratings are available.')
    st.markdown('#### Matchup highlights')
    if not d1_visible.empty:
        rated=d1_visible[d1_visible['Home ID'].astype(str).isin(ratings)&d1_visible['Away ID'].astype(str).isin(ratings)]
        scores=[]
        for _,g in rated[rated['Status']=='Scheduled'].iterrows():
            m=ratings[str(g['Home ID'])]-ratings[str(g['Away ID'])]+(0 if g['Venue']=='Neutral' else 3)
            scores.append((abs(m),f"{g['Away']} at {g['Home']}",m))
        for closeness,name,margin in sorted(scores)[:3]:
            st.caption(f"Close matchup · {name} · projected margin {closeness:.1f} points")
        if not scores:st.caption('Highlights will appear as D1 games are scheduled and rated.')
    else:st.caption('No verified D1 matchups are available in the selected date.')

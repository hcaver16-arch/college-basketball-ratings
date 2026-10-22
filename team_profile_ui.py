"""Courtside V54 team profile presentation. No impact on ratings or forecasts."""
from __future__ import annotations
import html
import pandas as pd
import streamlit as st


def _num(value, decimals=1, signed=False):
    try:
        v=float(value)
        if pd.isna(v): return '—'
        return f'{v:+.{decimals}f}' if signed else f'{v:.{decimals}f}'
    except (ValueError, TypeError):
        return '—'


def _lookup(table, tid):
    if not isinstance(table, pd.DataFrame) or table.empty or 'Team ID' not in table:
        return None
    match=table.loc[table['Team ID'].astype(str)==str(tid)]
    return match.iloc[0] if not match.empty else None


def _card(title, value, caption=''):
    st.markdown(f'<div class="cs-profile-stat"><div class="cs-profile-label">{html.escape(str(title))}</div><div class="cs-profile-number">{html.escape(str(value))}</div><div class="cs-profile-hint">{html.escape(str(caption))}</div></div>',unsafe_allow_html=True)


def render_team_profile(*, team, team_id, league, sport, ratings, games, preliminary, sos, sor, directory, history_loader):
    """Render the public profile. Call before optional legacy audit tools."""
    st.markdown('''<style>
    .cs-profile-head {background:#fff;border:1px solid #e2e8f0;border-radius:15px;padding:18px 20px;margin:4px 0 16px;border-top:5px solid #34465f}
    .cs-profile-head h2{margin:0;color:#23354b;font-size:1.65rem}
    .cs-profile-sub{color:#64748b;font-size:.9rem}
    .cs-profile-stat{background:#fff;border:1px solid #e2e8f0;padding:13px 16px;border-radius:12px;min-height:105px;margin:0 0 12px}
    .cs-profile-label{text-transform:uppercase;letter-spacing:.055em;font-size:.72rem;color:#64748b}
    .cs-profile-number{font-size:1.55rem;font-weight:720;color:#23354b;overflow-wrap:anywhere}
    .cs-profile-hint{font-size:.76rem;color:#718096}
    </style>''', unsafe_allow_html=True)
    rating=_lookup(ratings,team_id)
    experimental=_lookup(preliminary,team_id)
    sos_row=_lookup(sos,team_id)
    sor_row=_lookup(sor,team_id)
    dir_row=_lookup(directory,team_id)
    conference=str(dir_row.get('Conference','Conference not available')) if dir_row is not None else 'Conference not available'
    st.markdown(f'<div class="cs-profile-head"><div class="cs-profile-sub">{html.escape(league)} basketball · {html.escape(conference)}</div><h2>{html.escape(team)}</h2><div class="cs-profile-sub">Team scouting and season overview</div></div>',unsafe_allow_html=True)
    if 'cs_profile_logos' not in st.session_state: st.session_state.cs_profile_logos=False
    with st.expander('Team identity settings',expanded=False):
        st.checkbox('Display ESPN-hosted team logo (optional external image)',key='cs_profile_logos',help='External image hosting does not guarantee permission to reuse an image.')
    if st.session_state.cs_profile_logos:
        try:
            from team_identity import logo_uri
            url=logo_uri(team_id,league)
            if url: st.image(url,width=90)
        except Exception: pass
    else:
        st.caption('Team logo off · full school name remains visible')
    tabs=st.tabs(['Overview','Schedule','Roster','Analytics','Compare'])
    with tabs[0]:
        c1,c2,c3,c4=st.columns(4)
        with c1:_card('National rank', f"#{int(rating['Rank'])}" if rating is not None and pd.notna(rating.get('Rank')) else '—')
        with c2:_card('Power rating', _num(rating.get('Current power'),signed=True) if rating is not None else '—')
        with c3:_card('Games played', int(rating['Games played']) if rating is not None and pd.notna(rating.get('Games played')) else '—')
        with c4:_card('Roster-adjusted rating',_num(experimental.get('Experimental power'),signed=True) if experimental is not None else '—','Experimental · not validated')
        st.markdown('#### Rating history')
        history=history_loader(sport,str(team_id))
        if not isinstance(history,pd.DataFrame) or history.empty or 'Snapshot date' not in history or 'Current power' not in history:
            st.info('No saved rating history is available yet.')
        else:
            hist=history.copy()
            hist['Snapshot date']=pd.to_datetime(hist['Snapshot date'],errors='coerce')
            hist['Current power']=pd.to_numeric(hist['Current power'],errors='coerce')
            hist=hist.dropna(subset=['Snapshot date','Current power']).sort_values('Snapshot date').drop_duplicates('Snapshot date',keep='last')
            if hist['Snapshot date'].nunique() >= 2: st.line_chart(hist.set_index('Snapshot date')['Current power'])
            elif not hist.empty: st.info('One dated snapshot available. The trend chart appears after the next distinct update.')
            else: st.info('No valid dated rating points yet.')
        st.markdown('#### Next matchup')
        tg=_team_games(games,team_id)
        upcoming=tg[~tg['Status'].astype(str).str.lower().str.contains('final')].sort_values('Date') if not tg.empty and 'Status' in tg else pd.DataFrame()
        if upcoming.empty: st.caption('No upcoming game in the currently loaded schedule window.')
        else:
            g=upcoming.iloc[0]
            st.markdown(f"**{html.escape(str(g.get('Opponent','Unknown opponent')))}** · {html.escape(str(g.get('Date','Date unavailable')))} · {html.escape(str(g.get('Location','')))}")
        if experimental is not None:st.caption(str(experimental.get('Roster data status','Roster evidence is incomplete'))+' · Roster impact remains experimental.')
    with tabs[1]:
        st.markdown('#### Schedule and results')
        tg=_team_games(games,team_id)
        if tg.empty:st.info('No fixtures in the loaded date window. Broaden season coverage to see more.')
        else:
            fields=[c for c in ['Date','Opponent','Location','Status','Away score','Home score'] if c in tg]
            st.dataframe(tg[fields],hide_index=True,use_container_width=True,height=400)
            st.caption('Scores are shown in the original away/home order. Coverage depends on loaded ESPN schedules.')
    with tabs[2]:
        st.markdown('#### Roster continuity')
        if experimental is None:st.info('Returning-production data is not available for this team yet.')
        else:
            c1,c2=st.columns(2)
            with c1:_card('Experimental adjustment',_num(experimental.get('Roster adjustment'),signed=True),'Rating points; preliminary')
            with c2:_card('Returning minutes',_num(experimental.get('Returning minutes % (known only)'))+'%' if pd.notna(experimental.get('Returning minutes % (known only)')) else '—','Known records only')
            st.caption(str(experimental.get('Roster data status','Not verified')))
        st.info('Detailed player records, optional roster fetch, and collection-quality checks remain in Detailed data & tools below.')
    with tabs[3]:
        st.markdown('#### Team analytics')
        c1,c2,c3=st.columns(3)
        with c1:_card('Schedule strength',_num(sos_row.get('Full SOS'),signed=True) if sos_row is not None else '—','Model-based; loaded opponents')
        with c2:_card('Record strength',_num(sor_row.get('SOR score')) if sor_row is not None else '—','Availability depends on final games')
        with c3:_card('Preseason weight',_num(rating.get('Preseason weight')) if rating is not None else '—','Decreases as games are played')
        if sos_row is None:st.caption('Schedule-strength figures need rated opponent coverage.')
        if sor_row is None:st.caption('Strength of record becomes available once completed rated D1 games are recorded.')
        st.markdown('#### Rating composition')
        if rating is not None:
            columns=[c for c in ['Preseason rating','On-court rating','Preseason weight','Current power','Rating change'] if c in rating]
            if columns:st.dataframe(pd.DataFrame([rating[columns]]),hide_index=True,use_container_width=True)
    with tabs[4]:
        st.markdown('#### Compare with another team')
        if not isinstance(ratings,pd.DataFrame) or ratings.empty or 'Team' not in ratings:
            st.info('Load the national ratings to compare teams.')
        else:
            others=ratings.loc[ratings['Team ID'].astype(str)!=str(team_id)].dropna(subset=['Team']).sort_values('Team')
            if others.empty:st.caption('No other rated teams available.')
            else:
                opponent=st.selectbox('Compare against',others['Team'].astype(str).tolist(),key=f'profile_compare_{sport}_{team_id}')
                other=others.loc[others['Team'].astype(str)==opponent].iloc[0]
                comparison=pd.DataFrame([
                    {'Metric':'National power rank',str(team):f"#{int(rating['Rank'])}" if rating is not None and pd.notna(rating.get('Rank')) else '—',str(opponent):f"#{int(other['Rank'])}" if pd.notna(other.get('Rank')) else '—'},
                    {'Metric':'Power rating',str(team):_num(rating.get('Current power'),signed=True) if rating is not None else '—',str(opponent):_num(other.get('Current power'),signed=True)},
                    {'Metric':'Games played',str(team):int(rating['Games played']) if rating is not None and pd.notna(rating.get('Games played')) else '—',str(opponent):int(other['Games played']) if pd.notna(other.get('Games played')) else '—'},
                ])
                st.dataframe(comparison,hide_index=True,use_container_width=True)
                st.caption('Ratings are model estimates, not head-to-head game predictions. Venue is not included.')


def _team_games(games,tid):
    if not isinstance(games,pd.DataFrame) or games.empty or not {'Home ID','Away ID'}.issubset(games.columns):return pd.DataFrame()
    g=games.loc[(games['Home ID'].astype(str)==str(tid))|(games['Away ID'].astype(str)==str(tid))].copy()
    if g.empty:return g
    g['Opponent']=g.apply(lambda x:x['Away'] if str(x['Home ID'])==str(tid) else x['Home'],axis=1)
    g['Location']=g.apply(lambda x:'Neutral' if x.get('Venue')=='Neutral' else ('Home' if str(x['Home ID'])==str(tid) else 'Away'),axis=1)
    return g.sort_values('Date') if 'Date' in g else g

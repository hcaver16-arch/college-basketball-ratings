"""Courtside V54 team profile presentation. No impact on ratings or forecasts."""
from __future__ import annotations
import html
import re
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
    .cs-profile-stats-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
    .cs-profile-stats-grid .cs-profile-stat{min-width:0}
    @media(max-width:700px){.cs-profile-stats-grid{gap:6px}.cs-profile-stats-grid .cs-profile-stat{padding:9px 7px;min-height:76px}.cs-profile-stats-grid .cs-profile-number{font-size:1.1rem}.cs-profile-stats-grid .cs-profile-label{font-size:.59rem}}
    .cs-profile-head {background:#fff;border:1px solid #e2e8f0;border-radius:15px;padding:14px 18px;margin:4px 0 12px;border-top:5px solid #34465f}
    .cs-profile-head h2{margin:0;color:#23354b;font-size:1.65rem}
    .cs-profile-sub{color:#64748b;font-size:.9rem}
    .cs-profile-stat{background:#fff;border:1px solid #e2e8f0;padding:13px 16px;border-radius:12px;min-height:105px;margin:0 0 12px}
    .cs-profile-label{text-transform:uppercase;letter-spacing:.055em;font-size:.72rem;color:#64748b}
    .cs-profile-number{font-size:1.55rem;font-weight:720;color:#23354b;overflow-wrap:anywhere}
    .cs-profile-hint{font-size:.76rem;color:#718096}
    .cs-profile-initials{width:76px;height:76px;background:#23354b;border-radius:14px;display:flex;align-items:center;justify-content:center;font-weight:750;font-size:1.45rem;color:white}
    .cs-next-game{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:13px 16px}
    </style>''', unsafe_allow_html=True)
    rating=_lookup(ratings,team_id)
    experimental=_lookup(preliminary,team_id)
    sos_row=_lookup(sos,team_id)
    sor_row=_lookup(sor,team_id)
    dir_row=_lookup(directory,team_id)
    conference=str(dir_row.get('Conference','Conference not available')) if dir_row is not None else 'Conference not available'
    # Read the same single preference used by Matchup Analysis and the site header.
    external_logos = st.session_state.get("courtside_logos_enabled", True)
    short = str(team).strip()
    initials = ''.join(w[0] for w in re.findall(r"[A-Za-z]+",short)[:2]).upper() or '?'
    head_logo = None
    if external_logos:
        try:
            from team_identity import logo_uri
            head_logo=logo_uri(team_id,league)
        except Exception:
            pass
    hlogo,hname=st.columns([1,7],vertical_alignment='center')
    with hlogo:
        if head_logo:
            st.image(head_logo,width=82)
        else:
            st.markdown(f'<div class="cs-profile-initials">{html.escape(initials)}</div>',unsafe_allow_html=True)
    with hname:
        st.markdown(f'<div class="cs-profile-head"><div class="cs-profile-sub">{html.escape(league)} basketball · {html.escape(conference)}</div><h2>{html.escape(team)}</h2><div class="cs-profile-sub">Team scouting and season overview</div></div>',unsafe_allow_html=True)
    tabs=st.tabs(['Overview','Schedule','Roster','Analytics','Compare'])
    with tabs[0]:
        tg=_team_games(games,team_id)
        finals=tg[tg['Status'].astype(str).str.lower().str.contains('final')] if not tg.empty and 'Status' in tg else pd.DataFrame()
        wins=losses=0
        for _,result in finals.iterrows():
            try:
                a=float(result['Away score']);h=float(result['Home score'])
                if pd.isna(a) or pd.isna(h) or a==h:continue
                is_home=str(result.get('Home ID'))==str(team_id)
                won=(h>a) if is_home else (a>h)
                wins+=int(won);losses+=int(not won)
            except (KeyError,ValueError,TypeError):continue
        # A real CSS grid prevents Streamlit's automatic mobile column stacking.
        overview_stats = [
            ('National rank', f"#{int(rating['Rank'])}" if rating is not None and pd.notna(rating.get('Rank')) else '—'),
            ('Power rating', _num(rating.get('Current power'),signed=True) if rating is not None else '—'),
            ('Record', f'{wins}–{losses}'),
        ]
        cards = ''.join(
            f'<div class="cs-profile-stat"><div class="cs-profile-label">{html.escape(label)}</div>'
            f'<div class="cs-profile-number">{html.escape(value)}</div></div>'
            for label,value in overview_stats
        )
        st.markdown(f'<div class="cs-profile-stats-grid">{cards}</div>', unsafe_allow_html=True)
        st.markdown('#### Rating history')
        history=history_loader(sport,str(team_id))
        if not isinstance(history,pd.DataFrame) or history.empty or 'Snapshot date' not in history or 'Current power' not in history:
            st.caption('Rating history will appear as daily snapshots accumulate.')
        else:
            hist=history.copy()
            hist['Snapshot date']=pd.to_datetime(hist['Snapshot date'],errors='coerce',utc=True)
            hist['Current power']=pd.to_numeric(hist['Current power'],errors='coerce')
            hist=hist.dropna(subset=['Snapshot date','Current power']).sort_values('Snapshot date')
            hist['Day']=hist['Snapshot date'].dt.date
            hist=hist.drop_duplicates('Day',keep='last')
            if len(hist)>=3 and hist['Current power'].max()-hist['Current power'].min()>=0.1:
                st.line_chart(hist.set_index('Snapshot date')['Current power'])
            else:
                st.caption(f"Current rating: {_num(rating.get('Current power'),signed=True) if rating is not None else '—'} · More dated snapshots and rating movement are needed for a meaningful trend.")
        st.markdown('#### Next matchup')
        upcoming=tg[~tg['Status'].astype(str).str.lower().str.contains('final')].sort_values('Date') if not tg.empty and 'Status' in tg else pd.DataFrame()
        if upcoming.empty:
            st.caption('No future matchup found in the currently published season schedule.')
        else:
            g=upcoming.iloc[0]
            opp=html.escape(str(g.get('Opponent','Unknown opponent')))
            gd=html.escape(str(g.get('Date','Date unavailable')))
            loc=html.escape(str(g.get('Location','')))
            st.markdown(f'<div class="cs-next-game"><strong>{opp}</strong><div class="cs-profile-sub">{gd} · {loc}</div></div>',unsafe_allow_html=True)
            game_id=g.get('Game ID')
            if pd.notna(game_id) and st.button('View matchup →',key=f'profile_next_{sport}_{team_id}'):
                # Games normally shows only its selected calendar window.  Keep the
                # specific fixture in that window when navigating from a profile.
                # The schedule's Date column is already in Eastern calendar time.
                selected_date = pd.to_datetime(g.get('Date'), errors='coerce')
                if pd.notna(selected_date):
                    from datetime import date
                    day = selected_date.date()
                    if date(2026, 11, 1) <= day <= date(2027, 4, 12):
                        st.session_state['cs_calendar_anchor'] = day
                        st.session_state['cs_calendar_span'] = 'Selected day'
                    else:
                        st.session_state['cs_calendar_span'] = 'Full season (Nov–Apr)'
                else:
                    st.session_state['cs_calendar_span'] = 'Full season (Nov–Apr)'
                st.session_state['courtside_games_page'] = 1
                # Retain the exact fixture across a page switch. The Games calendar
                # may fetch a different window or the ESPN daily feed may omit it.
                st.session_state['courtside_selected_game_payload'] = g.to_dict()
                st.session_state['courtside_selected_game'] = str(game_id)
                st.session_state['courtside_page'] = 'Games'
                st.rerun()
        if experimental is not None:
            delta=pd.to_numeric(experimental.get('Roster adjustment'),errors='coerce')
            if pd.notna(delta) and abs(float(delta))>=0.05:
                st.caption(f"Experimental roster effect: {float(delta):+.1f} rating points · Not validated")
    with tabs[1]:
        st.markdown('#### Full-season schedule and results')
        tg=_team_games(games,team_id)
        if tg.empty:st.info('No fixtures were found in the current full-season feed. Some school schedules may not be published yet.')
        else:
            fields=[c for c in ['Date','Opponent','Location','Status','Away score','Home score'] if c in tg]
            st.dataframe(tg[fields],hide_index=True,use_container_width=True,height=400)
            st.caption(f'{len(tg)} published games loaded for this team, across the full season. Scores are in original away/home order. Missing or unpublished fixtures cannot be displayed.')
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

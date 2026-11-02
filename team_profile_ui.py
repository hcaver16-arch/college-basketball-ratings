"""Courtside V54 team profile presentation. No impact on ratings or forecasts."""
from __future__ import annotations
from preseason_profile_v101 import render_preseason_profile_v101
import html
import re
import pandas as pd
import streamlit as st
from efficiency_ui import render_team_efficiency
from raw_team_stats import team_raw_stats
from adjusted_display import merge_team_stats


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



def _history_rows(history):
    """Keep the last valid saved snapshot per day; never generate synthetic ratings."""
    if not isinstance(history,pd.DataFrame) or history.empty or not {'Snapshot date','Current power'}.issubset(history.columns):
        return pd.DataFrame(columns=['Snapshot date','Current power','Rank'])
    data=history.copy()
    data['Snapshot date']=pd.to_datetime(data['Snapshot date'],errors='coerce',utc=True)
    data['Current power']=pd.to_numeric(data['Current power'],errors='coerce')
    if 'Rank' in data:
        data['Rank']=pd.to_numeric(data['Rank'],errors='coerce')
    else:
        data['Rank']=float('nan')
    data=data.dropna(subset=['Snapshot date']).sort_values('Snapshot date')
    data['Day']=data['Snapshot date'].dt.date
    return data.drop_duplicates('Day',keep='last')


def _recent_results(team_games,team_id,limit=3):
    """Most recent actual completed results in the loaded schedule."""
    if not isinstance(team_games,pd.DataFrame) or team_games.empty or 'Status' not in team_games:
        return []
    finals=team_games[team_games['Status'].astype(str).str.contains('final',case=False,na=False)].copy()
    if finals.empty:return []
    if 'Date' in finals:
        finals=finals.sort_values('Date',ascending=False)
    rows=[]
    for _,game in finals.iterrows():
        home_id=str(game.get('Home ID'))
        home=home_id==str(team_id)
        ours=pd.to_numeric(game.get('Home score') if home else game.get('Away score'),errors='coerce')
        theirs=pd.to_numeric(game.get('Away score') if home else game.get('Home score'),errors='coerce')
        if pd.isna(ours) or pd.isna(theirs):continue
        opponent=str(game.get('Opponent','Unknown opponent'))
        result='W' if ours>theirs else ('L' if ours<theirs else 'T')
        rows.append((result,opponent,f'{int(ours)}–{int(theirs)}'))
        if len(rows)>=limit:break
    return rows


def _poll_positions(team_id,sport):
    """Published AP/Coaches ranks, if the existing cached ESPN feed has them."""
    result={'AP Top 25':'—','Coaches Poll':'—'}
    try:
        from published_polls_v137 import fetch_polls
        polls=fetch_polls(sport)
    except (ValueError,KeyError,TypeError,Exception):
        return result
    for label in result:
        poll=polls.get(label)
        if not isinstance(poll,dict):continue
        frame=poll.get('rows')
        row=_lookup(frame,team_id)
        if row is not None:
            try:result[label]=f"#{int(row['Rank'])}" if pd.notna(row.get('Rank')) else '—'
            except (ValueError,TypeError):pass
    return result


def _short_rating_row(label,value):
    return '<div class="cs198-snapshot-row"><span>'+html.escape(str(label))+'</span><strong>'+html.escape(str(value))+'</strong></div>'


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

    /* V198: balanced overview, compact team identity, aligned panels and durable trends */
    .cs198-header-stats{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:7px;margin:7px 0 10px}
    .cs198-header-kpi{background:#f3f7fd;border:1px solid #d8e4f3;border-radius:10px;padding:9px 10px;min-width:0}
    .cs198-header-label{color:#617792;font-size:.69rem;font-weight:650}
    .cs198-header-value{color:#19437b;font-size:1.05rem;font-weight:850;overflow-wrap:anywhere;line-height:1.35}
    .cs198-section{font-size:.88rem;color:#193a6a;font-weight:800;margin:3px 0 10px}
    .cs198-snapshot{border:1px solid #dbe6f3;border-radius:12px;background:#fff;padding:12px 13px;min-height:255px}
    .cs198-snapshot-row{display:flex;align-items:center;justify-content:space-between;gap:9px;padding:7px 0;border-bottom:1px solid #edf1f6;font-size:.77rem}
    .cs198-snapshot-row:last-child{border-bottom:0}
    .cs198-snapshot-row strong{color:#193e74;font-size:.84rem;white-space:nowrap}
    .cs198-recent{border:1px solid #dbe6f3;border-radius:12px;background:#fff;padding:12px 13px;min-height:255px}
    .cs198-recent-line{display:flex;justify-content:space-between;gap:8px;border-bottom:1px solid #edf1f6;padding:7px 0;font-size:.77rem}
    .cs198-recent-line strong{color:#153d70}
    .cs198-trend-title{display:flex;justify-content:space-between;gap:8px;font-size:.88rem;font-weight:800;color:#193a6a}
    .cs198-trend-delta{font-size:.74rem;font-weight:800;color:#0c7772}
    .cs198-trend-note{font-size:.72rem;color:#637a98;margin-top:5px}
    .st-key-cs198_rating_graph{border:1px solid #dbe6f3;border-radius:12px;background:#fff;padding:10px 12px 7px;min-height:255px}
    .st-key-cs198_rating_graph [data-testid="stVegaLiteChart"]{margin-top:-5px}
    .cs198-next{background:#eff5fd;border-radius:8px;padding:9px 10px;margin-top:10px}
    @media(max-width:850px){.cs198-header-stats{grid-template-columns:repeat(3,minmax(0,1fr))}}
    @media(max-width:500px){.cs198-header-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.cs198-header-kpi{padding:7px}}
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
    raw_stats = merge_team_stats(team_raw_stats(games,team_id,league), team_id, league)
    tg = _team_games(games,team_id)
    recent = _recent_results(tg,team_id)
    finals = (tg[tg['Status'].astype(str).str.contains('final',case=False,na=False)]
              if not tg.empty and 'Status' in tg else pd.DataFrame())
    wins=losses=0
    for _,result in finals.iterrows():
        a=pd.to_numeric(result.get('Away score'),errors='coerce')
        h=pd.to_numeric(result.get('Home score'),errors='coerce')
        if pd.isna(a) or pd.isna(h) or a==h:continue
        is_home=str(result.get('Home ID'))==str(team_id)
        won=(h>a) if is_home else (a>h)
        wins+=int(won);losses+=int(not won)
    polls=_poll_positions(team_id,sport)
    record=f'{wins}–{losses}'
    rank=f"#{int(rating['Rank'])}" if rating is not None and pd.notna(rating.get('Rank')) else '—'
    power=_num(rating.get('Current power'),signed=True) if rating is not None else '—'
    sos_value=_num(sos_row.get('Full SOS'),signed=True) if sos_row is not None else '—'
    sor_value=_num(sor_row.get('SOR score')) if sor_row is not None else '—'
    hlogo,hname=st.columns([1,7],vertical_alignment='center')
    with hlogo:
        if head_logo:
            st.image(head_logo,width=76)
        else:
            st.markdown(f'<div class="cs-profile-initials">{html.escape(initials)}</div>',unsafe_allow_html=True)
    with hname:
        st.markdown(
            '<div class="cs-profile-head">'
            f'<div class="cs-profile-sub">{html.escape(league)} basketball · {html.escape(conference)}</div>'
            f'<h2>{html.escape(team)}</h2>'
            f'<div class="cs-profile-sub">{record} · Current-season loaded results</div></div>',
            unsafe_allow_html=True
        )
    header_stats=[
        ('Courtside rank',rank),
        ('AP Top 25',polls['AP Top 25']),
        ('Coaches Poll',polls['Coaches Poll']),
        ('Power rating',power),
        ('Record',record),
    ]
    metrics=''.join(
        f'<div class="cs198-header-kpi"><div class="cs198-header-label">{html.escape(label)}</div>'
        f'<div class="cs198-header-value">{html.escape(str(value))}</div></div>'
        for label,value in header_stats
    )
    st.markdown('<div class="cs198-header-stats">'+metrics+'</div>',unsafe_allow_html=True)
    tabs=st.tabs(['Overview','Schedule','Statistics','Roster','Ratings'])
    history=_history_rows(history_loader(sport,str(team_id)))
    with tabs[0]:
        # V198: balanced three-column Overview with the saved trend front and center.
        snapshot_col,trend_col,recent_col=st.columns([1.10,1.65,1.10],gap="small")
        with snapshot_col:
            snapshot_rows=[
                ('Power rating',power),
                ('National power rank',rank),
                ('Preseason rating',_num(rating.get('Preseason rating'),signed=True) if rating is not None else '—'),
                ('Strength of schedule',sos_value),
                ('Strength of record',sor_value),
                ('Games played',str(int(rating['Games played'])) if rating is not None and pd.notna(rating.get('Games played')) else '—'),
            ]
            st.markdown(
                '<div class="cs198-snapshot"><div class="cs198-section">Team snapshot</div>'
                +''.join(_short_rating_row(label,value) for label,value in snapshot_rows)
                +'</div>',unsafe_allow_html=True
            )
        with trend_col:
            with st.container(key="cs198_rating_graph"):
                st.markdown('<div class="cs198-trend-title"><span>Power rating over time</span></div>',unsafe_allow_html=True)
                valid=history.dropna(subset=['Current power'])
                if len(valid)>=2:
                    change=float(valid.iloc[-1]['Current power'])-float(valid.iloc[0]['Current power'])
                    st.caption(f"{change:+.2f} since first saved snapshot · {len(valid)} dated snapshots")
                    st.line_chart(
                        valid.set_index('Snapshot date')[['Current power']],
                        use_container_width=True,height=190
                    )
                    if abs(change)<0.05:
                        st.caption("Rating is essentially unchanged across the available dates.")
                elif len(valid)==1:
                    st.metric("Saved power rating",f"{valid.iloc[0]['Current power']:+.2f}")
                    st.caption("One dated rating snapshot is available; a trend needs at least two dates.")
                else:
                    st.info("No saved rating snapshots are available for this team yet.")
                st.markdown(
                    '<div class="cs198-trend-note">Daily saved model ratings, not a projected '
                    'future trajectory or official NCAA ranking.</div>',unsafe_allow_html=True
                )
        with recent_col:
            rows=[
                '<div class="cs198-recent"><div class="cs198-section">Recent games</div>'
            ]
            if recent:
                rows.extend(
                    '<div class="cs198-recent-line"><span><strong>'+html.escape(result)
                    +'</strong> '+html.escape(opponent)+'</span><strong>'
                    +html.escape(score)+'</strong></div>'
                    for result,opponent,score in recent
                )
            else:
                rows.append(
                    '<div class="cs198-trend-note">No completed games in the loaded season.</div>'
                )
            rows.append('</div>')
            st.markdown(''.join(rows),unsafe_allow_html=True)
        st.markdown('#### Next matchup')
        upcoming=(tg[tg['Status'].astype(str).str.lower().eq('scheduled')].sort_values('Date')
                  if not tg.empty and 'Status' in tg else pd.DataFrame())
        if upcoming.empty:
            st.caption('No upcoming scheduled matchup in the loaded season.')
        else:
            g=upcoming.iloc[0]
            opp=html.escape(str(g.get('Opponent','Unknown opponent')))
            gd=html.escape(str(g.get('Date','Date unavailable')))
            loc=html.escape(str(g.get('Location','')))
            st.markdown(f'<div class="cs-next-game"><strong>{opp}</strong><div class="cs-profile-sub">{gd} · {loc}</div></div>',unsafe_allow_html=True)
            game_id=g.get('Game ID')
            if pd.notna(game_id) and st.button('View matchup →',key=f'profile_next_{sport}_{team_id}'):
                selected_date=pd.to_datetime(g.get('Date'),errors='coerce')
                if pd.notna(selected_date):
                    from datetime import date
                    day=selected_date.date()
                    if date(2026,11,1)<=day<=date(2027,4,12):
                        st.session_state['cs_calendar_anchor']=day
                        st.session_state['cs_calendar_span']='Selected day'
                    else:
                        st.session_state['cs_calendar_span']='Full season (Nov–Apr)'
                else:
                    st.session_state['cs_calendar_span']='Full season (Nov–Apr)'
                st.session_state['courtside_games_page']=1
                st.session_state['courtside_selected_game_payload']=g.to_dict()
                st.session_state['courtside_selected_game']=str(game_id)
                st.session_state['courtside_page']='Games'
                st.rerun()
        with st.expander("Preseason context and methodology",expanded=False):
            render_preseason_profile_v101(team_id=team_id,division=league,rating=rating,games=games)
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
        st.markdown('#### Team analytics')
        render_team_efficiency(raw_stats)
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
    with tabs[3]:
        st.markdown('#### Roster continuity')
        if experimental is None:st.info('Returning-production data is not available for this team yet.')
        else:
            c1,c2=st.columns(2)
            with c1:_card('Experimental adjustment',_num(experimental.get('Roster adjustment'),signed=True),'Rating points; preliminary')
            with c2:_card('Returning minutes',_num(experimental.get('Returning minutes % (known only)'))+'%' if pd.notna(experimental.get('Returning minutes % (known only)')) else '—','Known records only')
            st.caption(str(experimental.get('Roster data status','Not verified')))
        st.info('Detailed player records, optional roster fetch, and collection-quality checks remain in Detailed data & tools below.')
    with tabs[4]:
        st.markdown('#### Rating history and rank movement')
        valid_rating=history.dropna(subset=['Current power'])
        valid_rank=history.dropna(subset=['Rank'])
        if len(valid_rating)>=2:
            current=float(valid_rating.iloc[-1]['Current power'])
            movement=current-float(valid_rating.iloc[0]['Current power'])
            st.metric('Latest saved power',f'{current:+.2f}',delta=f'{movement:+.2f} since first snapshot')
            st.line_chart(valid_rating.set_index('Snapshot date')[['Current power']],use_container_width=True)
        elif len(valid_rating)==1:
            st.metric('Saved power',f"{valid_rating.iloc[0]['Current power']:+.2f}")
            st.caption('A second dated snapshot is needed to display rating movement.')
        else:
            st.info('No dated rating history is available yet.')
        if len(valid_rank)>=2:
            rank_delta=int(valid_rank.iloc[0]['Rank']-valid_rank.iloc[-1]['Rank'])
            st.metric('Current saved national rank',f"#{int(valid_rank.iloc[-1]['Rank'])}",delta=f"{rank_delta:+d} positions")
            st.line_chart(valid_rank.set_index('Snapshot date')[['Rank']],use_container_width=True)
            st.caption('Smaller rank numbers are better.')
        if not history.empty:
            with st.expander('Saved daily rating records',expanded=False):
                display=[key for key in ['Snapshot date','Rank','Current power','Preseason rating','On-court rating','Games played','Preseason weight'] if key in history.columns]
                st.dataframe(history[display].sort_values('Snapshot date',ascending=False),hide_index=True,use_container_width=True)
        st.caption('Trend lines show saved model snapshots; without completed games, ratings may remain flat.')
        with st.expander('Compare with another team',expanded=False):
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

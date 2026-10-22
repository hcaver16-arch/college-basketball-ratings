"""Courtside V58: conference overview derived from verified D1 saved team ratings."""
from __future__ import annotations
import html
import math
import pandas as pd
import streamlit as st


def _number(v, signed=True):
    try:
        x=float(v)
        return (f'{x:+.1f}' if signed else f'{x:.1f}') if math.isfinite(x) else '—'
    except (TypeError, ValueError):
        return '—'


def render_conferences(ratings: pd.DataFrame, verified_d1_ids: set[str], league: str):
    st.markdown('''<style>
    .cc-head{background:white;border:1px solid #e2e8f0;border-radius:14px;padding:16px 20px;margin-bottom:12px}
    .cc-head h2{font-size:1.5rem;color:#23354b;margin:0 0 5px}
    .cc-note{color:#68798d;font-size:.85rem}
    .cc-row{background:#fff;border:1px solid #e4eaf0;border-radius:11px;padding:12px 16px;color:#243449}
    .cc-name{font-weight:650;color:#23354b}
    .cc-muted{font-size:.8rem;color:#718096}
    .cc-number{font-weight:700;color:#23354b;font-variant-numeric:tabular-nums;text-align:right}
    </style>''',unsafe_allow_html=True)
    st.markdown(f'<div class="cc-head"><h2>Conference Power Rankings</h2><div class="cc-note">{html.escape(league)} Division I · Saved team-rating averages · Not conference standings</div></div>',unsafe_allow_html=True)
    if not isinstance(ratings,pd.DataFrame) or ratings.empty:
        st.info('Conference power rankings will appear once saved ratings are available.')
        return
    if not {'Team ID','Team','Conference','Current power'}.issubset(ratings.columns):
        st.warning('The saved team data does not include the fields needed for conference comparisons.')
        return
    if not verified_d1_ids:
        st.warning('D1 conference membership is unavailable, so conference rankings are hidden rather than including unverified teams.')
        return
    data=ratings.copy()
    data['Team ID']=data['Team ID'].astype(str)
    data=data[data['Team ID'].isin({str(x) for x in verified_d1_ids})].copy()
    data['Current power']=pd.to_numeric(data['Current power'], errors='coerce')
    data=data.dropna(subset=['Current power','Conference','Team'])
    data=data[~data['Conference'].astype(str).str.contains('Unassigned|not verified|Unknown',case=False,na=False)]
    data=data.drop_duplicates('Team ID')
    if data.empty:
        st.info('No verified rated D1 conference members found.')
        return
    summary=data.groupby('Conference',as_index=False).agg(Teams=('Team ID','nunique'),Average=('Current power','mean'),Median=('Current power','median'))
    top5=data.groupby('Conference')['Current power'].apply(lambda a:a.nlargest(5).mean()).rename('Top five').reset_index()
    summary=summary.merge(top5,on='Conference').sort_values('Average',ascending=False).reset_index(drop=True)
    summary['Power rank']=summary.index+1
    search=st.text_input('Find conference',placeholder='Search conferences…',key='cc_find')
    sort=st.selectbox('Compare by',['Average team power','Top-five power','Median team power'],key='cc_sort')
    key={'Average team power':'Average','Top-five power':'Top five','Median team power':'Median'}[sort]
    shown=summary[summary['Conference'].astype(str).str.contains(search,case=False,regex=False,na=False)] if search else summary
    shown=shown.sort_values(key,ascending=False).reset_index(drop=True)
    shown['Displayed rank']=shown.index+1
    st.caption(f'{len(shown)} conferences · Ranked by {sort.lower()} · D1 teams with saved ratings only')
    for _,item in shown.iterrows():
        c1,c2,c3,c4=st.columns([.5,3.1,1.3,1.3],vertical_alignment='center')
        with c1: st.markdown(f'<div class="cc-number">#{int(item["Displayed rank"])}</div>',unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="cc-name">{html.escape(str(item["Conference"]))}</div><div class="cc-muted">{int(item["Teams"])} rated D1 teams</div>',unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="cc-number">{_number(item[key])}</div><div class="cc-muted" style="text-align:right">{html.escape(sort)}</div>',unsafe_allow_html=True)
        with c4:
            if st.button('View teams →',key=f'cc_open_{league}_{item["Conference"]}',use_container_width=True):
                st.session_state['cc_breakdown']=str(item['Conference'])
                st.rerun()
        st.divider()
    names=summary['Conference'].astype(str).tolist()
    preferred=st.session_state.get('cc_breakdown')
    initial=names.index(preferred) if preferred in names else 0
    selected=st.selectbox('Conference team breakdown',names,index=initial,key='cc_breakdown')
    member=data[data['Conference'].astype(str)==selected].sort_values('Current power',ascending=False)
    st.markdown(f'### {selected} teams')
    st.caption(f'{len(member)} rated D1 schools in this conference · Select any school to open its profile')
    for ix,(_,team) in enumerate(member.iterrows(),start=1):
        a,b,c=st.columns([3,.9,1.15],vertical_alignment='center')
        with a: st.markdown(f'<div class="cc-name">{ix}. {html.escape(str(team["Team"]))}</div>',unsafe_allow_html=True)
        with b: st.markdown(f'<div class="cc-number">{_number(team["Current power"])}</div>',unsafe_allow_html=True)
        with c:
            if st.button('View team →',key=f'cc_team_{league}_{team["Team ID"]}',use_container_width=True):
                st.session_state['v12_team_pick']=str(team['Team'])
                st.session_state['courtside_page']='Teams'
                st.rerun()
    with st.expander('Advanced conference data & download',expanded=False):
        st.dataframe(summary[['Power rank','Conference','Teams','Average','Median','Top five']],hide_index=True,use_container_width=True)
        st.download_button('Download conference power rankings',summary.to_csv(index=False).encode('utf-8'),'courtside_conference_power.csv','text/csv')
        st.caption('Conference power is an unweighted summary of rated teams, not a win-loss standing or official conference ranking. Coverage can affect averages.')

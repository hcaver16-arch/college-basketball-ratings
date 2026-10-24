"""Courtside V56: searchable paginated public rankings without modifying ratings."""
from __future__ import annotations
import html
import math
import pandas as pd
import streamlit as st


MOBILE_CARD_STYLE = '''<style>
.cs79-grid{display:grid!important;grid-template-columns:38px minmax(0,1fr) minmax(76px,max-content)!important;align-items:center!important;gap:12px!important;width:100%!important;min-width:0!important;color:#23354b}
.cs79-rank{color:#64748b;font-weight:750;font-size:.9rem}
.cs79-team{min-width:0!important;overflow-wrap:anywhere!important}
.cs79-name{font-weight:700;font-size:.96rem;line-height:1.25;color:#23354b}
.cs79-meta{font-size:.77rem;color:#718096;margin-top:4px}
.cs79-result{text-align:right!important;min-width:0!important;justify-self:end!important}
.cs79-number{font-size:1.08rem;color:#23354b;font-weight:750;white-space:nowrap}
.cs79-label{color:#718096;font-size:.69rem;line-height:1.22;overflow-wrap:anywhere}
@media(max-width:640px){.cs79-grid{grid-template-columns:29px minmax(0,1fr) 80px!important;gap:8px!important}.cs79-name{font-size:.87rem}.cs79-meta{font-size:.71rem}.cs79-number{font-size:1rem}.cs79-label{font-size:.63rem}}
</style>'''

def _fmt(value, signed=False):
    try:
        x=float(value)
        if not math.isfinite(x): return '—'
        return f'{x:+.1f}' if signed else f'{x:.1f}'
    except (TypeError, ValueError):
        return '—'


def render_rankings(ratings: pd.DataFrame, preliminary: pd.DataFrame, league: str, verified_d1_ids: set[str]):
    st.markdown('''<style>
    .cr-head{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:17px 20px;margin-bottom:14px}
    .cr-head h2{font-size:1.5rem;color:#243449;margin:0 0 5px}
    .cr-sub{font-size:.86rem;color:#69798c}
    .cr-row{background:#fff;border:1px solid #e3e8ef;border-radius:10px;padding:10px 15px;margin:0 0 4px;min-height:60px;display:flex;align-items:center;gap:14px}
    .cr-rank{width:35px;font-weight:700;color:#64748b;flex-shrink:0}
    .cr-dot{width:8px;height:8px;border-radius:50%;background:#34465f;flex-shrink:0}
    .cr-name{font-size:.96rem;color:#23354b;font-weight:650;overflow-wrap:anywhere}
    .cr-conf{font-size:.76rem;color:#728096}
    .cr-value{font-weight:750;color:#23354b;font-variant-numeric:tabular-nums;white-space:nowrap;text-align:right}
    .cr-label{font-size:.71rem;color:#728096;text-align:right}
    </style>''',unsafe_allow_html=True)
    st.markdown(MOBILE_CARD_STYLE, unsafe_allow_html=True)
    st.markdown(f'<div class="cr-head"><h2>National Power Rankings</h2><div class="cr-sub">{html.escape(league)} Division I · Saved baseline ratings · Select a team for its scouting report</div></div>',unsafe_allow_html=True)
    if not isinstance(ratings,pd.DataFrame) or ratings.empty:
        st.info('Rankings will appear once saved ratings are available.')
        return
    data=ratings.copy()
    if 'Team' not in data or 'Current power' not in data:
        st.warning('Saved ratings do not contain the expected team and rating columns.')
        return
    data['Current power']=pd.to_numeric(data['Current power'],errors='coerce')
    data=data.dropna(subset=['Team','Current power']).copy()
    # D1 membership comes from the current-season ESPN conference hierarchy,
    # not the rated schedule or the conference label in the saved snapshot.
    # Fail closed instead of treating unverified/non-D1 opponents as D1.
    if 'Team ID' not in data.columns:
        st.warning('Cannot verify Division I membership: saved ratings lack Team ID.')
        return
    if not verified_d1_ids:
        st.warning('Division I membership is currently unavailable. Rankings are hidden rather than including unverified schools.')
        return
    allowed = {str(team_id) for team_id in verified_d1_ids}
    data['Team ID'] = data['Team ID'].astype(str)
    data = data[data['Team ID'].isin(allowed)].copy()
    if data.empty:
        st.info('No rated, verified Division I teams are available yet.')
        return
    if 'Conference' not in data: data['Conference']='Unassigned'
    data['Conference']=data['Conference'].fillna('Unassigned').astype(str)
    exp_available=isinstance(preliminary,pd.DataFrame) and not preliminary.empty and {'Team ID','Experimental power'}.issubset(preliminary.columns) and 'Team ID' in data.columns
    if exp_available:
        extra=preliminary[['Team ID','Experimental power','Roster adjustment']].copy() if 'Roster adjustment' in preliminary else preliminary[['Team ID','Experimental power']].copy()
        extra['Team ID']=extra['Team ID'].astype(str)
        data['Team ID']=data['Team ID'].astype(str)
        data=data.merge(extra.drop_duplicates('Team ID'),on='Team ID',how='left',suffixes=('','_experiment'))
    c1,c2,c3=st.columns([2.3,1.7,1.5])
    with c1: query=st.text_input('Search teams',placeholder='Search by school or mascot…',key='cr_search')
    with c2:
        conferences=['All conferences']+sorted(c for c in data['Conference'].unique() if c and c!='Unassigned')
        conference=st.selectbox('Conference',conferences,key='cr_conference')
    with c3:
        sorts=['Power rating','School name','Games played']
        if exp_available: sorts.append('Experimental rating')
        sort=st.selectbox('Sort by',sorts,key='cr_sort')
    if query.strip(): data=data[data['Team'].astype(str).str.contains(query.strip(),case=False,regex=False,na=False)]
    if conference!='All conferences': data=data[data['Conference']==conference]
    order_col={'Power rating':'Current power','School name':'Team','Games played':'Games played','Experimental rating':'Experimental power'}.get(sort,'Current power')
    if order_col not in data:order_col='Current power'
    data=data.sort_values(order_col,ascending=(sort=='School name'),na_position='last',kind='stable')
    total=len(data)
    st.caption(f'{total:,} matching verified Division I teams · Rankings are model estimates, not NCAA NET rankings.')
    if not total:
        st.info('No teams match these filters.')
        return
    per_page=25
    max_page=max(1,math.ceil(total/per_page))
    page=st.number_input('Page',min_value=1,max_value=max_page,value=1,step=1,key='cr_page') if max_page>1 else 1
    start=(int(page)-1)*per_page
    shown=data.iloc[start:start+per_page]
    for j,(_,item) in enumerate(shown.iterrows()):
        rank=item.get('Rank')
        try: rank_label=f'#{int(rank)}' if pd.notna(rank) else '—'
        except (TypeError,ValueError):rank_label='—'
        v=item.get('Experimental power') if sort=='Experimental rating' else item['Current power']
        label='Experimental' if sort=='Experimental rating' else 'Power rating'
        with st.container(border=True):
            st.html(
                '<div class="cs79-grid">'
                f'<div class="cs79-rank">{html.escape(rank_label)}</div>'
                '<div class="cs79-team">'
                f'<div class="cs79-name">{html.escape(str(item["Team"]))}</div>'
                f'<div class="cs79-meta">{html.escape(str(item["Conference"]))}</div>'
                '</div><div class="cs79-result">'
                f'<div class="cs79-number">{html.escape(_fmt(v, True))}</div>'
                f'<div class="cs79-label">{html.escape(label)}</div>'
                '</div></div>'
            )
            if st.button('View team →',key=f'cr_open_{league}_{item.get("Team ID",str(item["Team"]))}_{start+j}',use_container_width=True):
                st.session_state['v12_team_pick']=str(item['Team'])
                st.session_state['courtside_page']='Teams'
                st.rerun()
    if max_page>1:st.caption(f'Page {page} of {max_page} · Showing {start+1}–{min(total,start+per_page)}')
    with st.expander('Advanced rankings and downloads',expanded=False):
        cols=[c for c in ['Rank','Team','Conference','Current power','Games played','Preseason rating','Experimental power','Roster adjustment'] if c in data]
        st.dataframe(data[cols],hide_index=True,use_container_width=True,height=400)
        st.download_button('Download filtered rankings CSV',data[cols].to_csv(index=False).encode('utf-8'),f'{league.lower().replace(" ", "_")}_courtside_rankings.csv','text/csv')
        st.caption('Experimental player effects are preliminary and unvalidated; default ordering uses baseline power ratings.')

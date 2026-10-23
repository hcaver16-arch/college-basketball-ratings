"""Courtside V66: consistent, navigable SOS and SOR presentation; no model changes."""
from __future__ import annotations
import html
import math
import pandas as pd
import streamlit as st

STYLE='''<style>
.cs-head{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:18px 20px;margin:0 0 15px}
.cs-head h2{font-size:1.5rem;color:#23354b;margin:0 0 5px}
.cs-head p{color:#66788b;font-size:.88rem;margin:0}
.cs-row{background:#fff;border:1px solid #e3e8ef;border-radius:11px;min-height:66px;padding:11px 14px;display:flex;gap:12px;align-items:center;margin:0 0 5px;color:#23354b}
.cs-rank{min-width:44px;color:#67788e;font-size:.9rem;font-weight:700}
.cs-name{color:#23354b;font-weight:700;font-size:.96rem;overflow-wrap:anywhere}
.cs-conf{font-size:.76rem;color:#728096}
.cs-metric{text-align:right;font-size:1.02rem;font-weight:750;color:#23354b;white-space:nowrap}
.cs-submetric{text-align:right;color:#718096;font-size:.72rem}
.cs-muted{font-size:.74rem;color:#906a34}
</style>'''

def _s(value, fmt='.1f', signed=False):
    try:
        x=float(value)
        if not math.isfinite(x): return '—'
        return format(x,('+' if signed else '')+fmt)
    except (TypeError,ValueError):return '—'

def _rank(value):
    try:
        if pd.isna(value):return '—'
        return '#'+str(int(float(value)))
    except (TypeError,ValueError):return '—'

def _base(df,verified_ids):
    if not isinstance(df,pd.DataFrame) or df.empty:return pd.DataFrame()
    if not {'Team','Team ID'}.issubset(df.columns):return pd.DataFrame()
    if not verified_ids:return pd.DataFrame()
    d=df.copy()
    d['Team ID']=d['Team ID'].astype(str)
    d=d[d['Team ID'].isin({str(i) for i in verified_ids})].copy()
    if 'Conference' not in d:d['Conference']='Unassigned'
    d['Conference']=d['Conference'].fillna('Unassigned').astype(str)
    return d.dropna(subset=['Team']).drop_duplicates('Team ID')

def _navigate(item):
    st.session_state['v12_team_pick']=str(item['Team'])
    st.session_state['courtside_page']='Teams'
    st.rerun()

def _render(df,league,kind,score_col,rank_col,details,sort_options):
    x,y,z=st.columns([2.3,1.8,1.65])
    with x:q=st.text_input('Search teams',placeholder='School or mascot…',key=f'cs_{kind}_query')
    with y:conf=st.selectbox('Conference',['All conferences']+sorted(c for c in df['Conference'].unique() if c and c!='Unassigned'),key=f'cs_{kind}_conf')
    with z:sort=st.selectbox('Sort by',list(sort_options),key=f'cs_{kind}_sort')
    if q.strip():df=df[df['Team'].astype(str).str.contains(q.strip(),case=False,regex=False,na=False)]
    if conf!='All conferences':df=df[df['Conference']==conf]
    col=sort_options[sort]
    if col not in df.columns:col=score_col
    df=df.assign(_sortvalue=pd.to_numeric(df[col],errors='coerce'))
    df=df.sort_values(['_sortvalue','Team'],ascending=[False,True],na_position='last',kind='stable')
    if kind == 'sos':
        # Visible, non-authoritative positions even when schedules aren't rank-eligible.
        # Use the chosen SOS measure, not the possibly unrelated sorting column.
        valid_scores=pd.to_numeric(df[score_col],errors='coerce')
        score_positions=valid_scores.rank(method='min',ascending=False)
        df=df.assign(_display_sos_position=score_positions)
    n=len(df)
    st.caption(f'{n:,} matching D1 teams · Higher {kind.upper()} scores indicate stronger schedule difficulty or résumé strength, respectively. SOS numbers without verified coverage are display positions, not certified ranks.')
    if n==0:st.info('No teams match these filters.');return
    page_size=25
    pages=max(1,math.ceil(n/page_size))
    page=st.number_input('Page',min_value=1,max_value=pages,value=1,step=1,key=f'cs_{kind}_page') if pages>1 else 1
    start=(int(page)-1)*page_size
    for i,(_,r) in enumerate(df.iloc[start:start+page_size].iterrows()):
        a,b,c=st.columns([5,1.5,1.35],vertical_alignment='center',gap='small')
        title=html.escape(str(r['Team']))
        conference=html.escape(str(r['Conference']))
        rk=_rank(r.get(rank_col))
        if kind == 'sos' and rk == '—':
            rk=_rank(r.get('_display_sos_position'))
        rk=html.escape(rk)
        with a:
            st.markdown(f'<div class="cs-row"><span class="cs-rank">{rk}</span><div><div class="cs-name">{title}</div><div class="cs-conf">{conference}</div></div></div>',unsafe_allow_html=True)
        with b:
            val=_s(r.get(score_col),signed=True)
            if kind=='sor' and pd.isna(r.get(rank_col)):
                sub='Not rank-eligible'
            elif kind=='sos' and pd.isna(r.get(rank_col)):
                sub='Unverified SOS position'
            else:sub=score_col
            st.markdown(f'<div class="cs-metric">{html.escape(val)}</div><div class="cs-submetric">{html.escape(sub)}</div>',unsafe_allow_html=True)
        with c:
            if st.button('View team →',key=f'cs_{kind}_{league}_{r["Team ID"]}_{start+i}',use_container_width=True):_navigate(r)
    if pages>1:st.caption(f'Page {page} of {pages} · Showing {start+1}–{min(start+page_size,n)}')
    with st.expander('Advanced statistics, coverage and CSV download'):
        cols=[c for c in details if c in df.columns]
        st.dataframe(df[cols],hide_index=True,use_container_width=True,height=420)
        st.download_button('Download filtered CSV',df[cols].to_csv(index=False).encode(),f'{kind}_{league.lower().replace(" ","_")}.csv','text/csv',key=f'cs_{kind}_csv')

def render_sos(df,league,verified_d1_ids):
    st.markdown(STYLE,unsafe_allow_html=True)
    st.markdown('<div class="cs-head"><h2>Strength of Schedule</h2><p>How difficult each school’s Division I opponents are, based on Courtside power ratings. Not an official NCAA metric.</p></div>',unsafe_allow_html=True)
    data=_base(df,verified_d1_ids)
    if data.empty:
        st.info('SOS is not available for verified D1 teams yet. Use Full season coverage and calculate ratings in Model Lab.');return
    st.warning('SOS positions are provisional and based on the available full-season schedule feed. When a team fails coverage requirements, its number is a display position—not a verified SOS rank.')
    scope=st.segmented_control('Schedule scope',['Full SOS','Played SOS','Remaining SOS'],default='Full SOS',key='cs_sos_scope')
    if scope is None:scope='Full SOS'
    if scope not in data:st.info('The selected schedule measure is not available.');return
    opts={'Schedule difficulty':scope,'Team name':'Team','D1 games loaded':'D1 games loaded'}
    # Alphabetical sort is managed separately to avoid numerical conversion of school names.
    if 'Team name' in opts:
        opts.pop('Team name')
    _render(data,league,'sos',scope,'SOS rank (provisional)',
            ['SOS rank (provisional)','Team','Conference','Full SOS','Played SOS','Remaining SOS','D1 games loaded','Rated games','Rating coverage %','Schedule coverage status','Coverage explanation'],opts)
    with st.expander('What does SOS mean?'):
        st.write('Full SOS describes the average difficulty of rated D1 opponents in the loaded schedule. Played and remaining SOS split opponents according to game status. A higher value means tougher opposition in this rating system. Ratings and coverage may change as more schedules are collected.')

def render_sor(df,league,verified_d1_ids):
    st.markdown(STYLE,unsafe_allow_html=True)
    st.markdown('<div class="cs-head"><h2>Strength of Record</h2><p>How impressive a team’s achieved record is given its rated Division I opponents and game locations.</p></div>',unsafe_allow_html=True)
    data=_base(df,verified_d1_ids)
    if data.empty:
        st.info('SOR will populate after completed current-season D1 games are available and ratings have been calculated.');return
    st.warning('SOR is provisional, not ESPN’s official SOR. At least five rated completed D1 games are required for a provisional rank; calculations use an uncalibrated 11-point margin uncertainty.')
    if 'SOR score' not in data:st.info('The saved SOR data does not include scores yet.');return
    eligible= pd.to_numeric(data.get('SOR games',pd.Series(index=data.index,dtype=float)),errors='coerce').ge(5)
    data=data.copy()
    # The upstream saved rank should be authoritative; never synthesize a rank from incomplete data.
    data['SOR eligibility']=eligible.map({True:'Five-game threshold met',False:'Fewer than five rated games'})
    _render(data,league,'sor','SOR score','SOR rank (provisional)',
            ['SOR rank (provisional)','Team','Conference','Wins','Losses','SOR games','Reference expected wins','Wins above expected','SOR score','SOR eligibility'],
            {'SOR score':'SOR score','Wins above expected':'Wins above expected','Completed D1 games':'SOR games'})
    with st.expander('What does SOR mean?'):
        st.write('Courtside estimates how likely a reference-strength D1 team would be to match or exceed each school’s wins against the same rated opponents and locations. SOR = −log10(probability). Larger values indicate more impressive results. Only completed D1-v-D1 games with rated opponents count; missing games and uncertainty affect the estimate.')

"""Courtside V77: mobile-safe SOS/SOR rows; no model changes."""
from __future__ import annotations
import html
import math
import pandas as pd
import streamlit as st

STYLE='''<style>
.cs-head{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:18px 20px;margin:0 0 15px}
.cs-head h2{font-size:1.5rem;color:#23354b;margin:0 0 5px}
.cs-head p{color:#66788b;font-size:.88rem;margin:0}
/* One cohesive native Streamlit bordered container per team */
.st-key-cs_strength_card [data-testid="stVerticalBlock"]{gap:.20rem!important}
.st-key-cs_strength_card button{margin-top:0!important}
.cs-team-grid{box-sizing:border-box;display:grid!important;grid-template-columns:38px minmax(0,1fr) max-content!important;gap:12px!important;align-items:center!important;width:100%!important;max-width:100%!important;min-width:0!important;color:#23354b}
.cs-team-rank{font-weight:700;color:#67788e;font-size:.91rem}
.cs-team-school{min-width:0!important;overflow-wrap:anywhere!important;word-break:normal!important}
.cs-team-name{font-size:.96rem;font-weight:700;line-height:1.28}
.cs-team-conf{font-size:.78rem;color:#718096;margin-top:4px}
.cs-team-score{min-width:68px;max-width:95px;text-align:right!important;justify-self:end!important;align-self:center!important}
.cs-team-value{font-weight:750;font-size:1.1rem;white-space:nowrap}
.cs-team-detail{font-size:.69rem;color:#718096;line-height:1.2;overflow-wrap:anywhere}
@media(max-width:640px){
 .cs-team-grid{grid-template-columns:30px minmax(0,1fr) 68px!important;gap:8px!important}
 .cs-team-name{font-size:.89rem}.cs-team-conf{font-size:.72rem}
 .cs-team-value{font-size:1rem}.cs-team-detail{font-size:.65rem}
}
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
        title=html.escape(str(r['Team']))
        conference=html.escape(str(r['Conference']))
        rk=_rank(r.get(rank_col))
        if kind == 'sos' and rk == '—':
            rk=_rank(r.get('_display_sos_position'))
        val=_s(r.get(score_col),signed=True)
        if kind=='sor' and pd.isna(r.get(rank_col)):
            sub='Not rank-eligible'
        elif kind=='sos' and pd.isna(r.get(rank_col)):
            sub='Unverified position'
        else:
            sub=score_col
        # Keep the row and its native navigation button in ONE bordered Streamlit
        # container; separate HTML cards and buttons got split by the mobile layout.
        with st.container(border=True):
            st.html(
                '<div class="cs-team-grid">'
                f'<div class="cs-team-rank">{html.escape(rk)}</div>'
                '<div class="cs-team-school">'
                f'<div class="cs-team-name">{title}</div>'
                f'<div class="cs-team-conf">{conference}</div>'
                '</div>'
                '<div class="cs-team-score">'
                f'<div class="cs-team-value">{html.escape(val)}</div>'
                f'<div class="cs-team-detail">{html.escape(sub)}</div>'
                '</div></div>'
            )
            if st.button('View team →',key=f'cs_{kind}_{league}_{r["Team ID"]}_{start+i}',use_container_width=True):
                _navigate(r)
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

"""Courtside V58: conference overview derived from verified D1 saved team ratings."""
from __future__ import annotations
import html
import math
import pandas as pd
import streamlit as st
from conference_standings import standings_for_conference, provisional_bracket


def _number(v, signed=True):
    try:
        x=float(v)
        return (f'{x:+.1f}' if signed else f'{x:.1f}') if math.isfinite(x) else '—'
    except (TypeError, ValueError):
        return '—'


def render_conferences(ratings: pd.DataFrame, verified_d1_ids: set[str], league: str, games: pd.DataFrame | None = None, coverage: str = "Selected schedule window"):
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
    # A selected conference is rendered as a separate view at the top of the page.
    # It never appears beneath the full list of conferences.
    selected = st.session_state.get('cc_breakdown')
    names = summary['Conference'].astype(str).tolist()
    if selected not in names:
        st.session_state.pop('cc_breakdown', None)
        selected = None

    if selected:
        if st.button('← Back to all conferences', key='cc_back_to_all'):
            st.session_state.pop('cc_breakdown', None)
            st.rerun()
        conference_summary = summary.loc[summary['Conference'].astype(str) == selected].iloc[0]
        st.markdown(f'<div class="cc-head"><h2>{html.escape(selected)}</h2>'
                    f'<div class="cc-note">{int(conference_summary["Teams"])} rated Division I teams '
                    f'· Conference power rank #{int(conference_summary["Power rank"])} '
                    f'· Average power {_number(conference_summary["Average"])}</div></div>',
                    unsafe_allow_html=True)
        member = data[data['Conference'].astype(str) == selected].sort_values('Current power', ascending=False)
        st.markdown('### Conference standings')
        standings = standings_for_conference(member, games)
        st.caption(f'From completed games in: {coverage}. Conference games are contests between current verified members. This is NOT an official league standing or tiebreak calculation.')
        if not standings.empty:
            shown_standings = standings.copy()
            shown_standings.insert(0, 'Provisional seed', range(1,len(shown_standings)+1))
            shown_standings['Conf. record'] = shown_standings['Conference W'].astype(str)+'–'+shown_standings['Conference L'].astype(str)
            shown_standings['Overall loaded'] = shown_standings['Overall W'].astype(str)+'–'+shown_standings['Overall L'].astype(str)
            shown_standings['Conf. win %'] = shown_standings['Conference PCT'].map(lambda x:f'{x:.3f}')
            st.dataframe(shown_standings[['Provisional seed','Team','Conf. record','Conf. win %','Overall loaded']],hide_index=True,use_container_width=True)
            played_conf = int((standings['Conference W']+standings['Conference L']).sum()/2)
            if played_conf == 0:
                st.info('No completed conference games in the loaded schedule yet. Seed order below is an illustrative preseason placeholder determined by rating, not earned standings.')
            elif coverage != 'Full season (Nov–Apr)':
                st.warning('Only a portion of the schedule is loaded. Choose Full season (Nov–Apr) in the sidebar for more complete standings.')
            st.markdown('### Conference championship preview')
            st.caption('Provisional seed order follows the standings above. Ties are broken by Courtside rating for display only—not by official conference procedures. Actual tournament eligibility, participation limits, byes, and reseeding differ by conference and gender. Do not treat this as the official bracket.')
            with st.expander('Illustrative all-teams single-elimination pairings (NOT official format)',expanded=False):
                if played_conf == 0:
                    st.info('Pairings are based only on a preseason placeholder order.')
                for hi,first,lo,second in provisional_bracket(standings):
                    if second=='BYE':
                        st.write(f'Seed {hi}: {first} — illustrative bye')
                    else:
                        st.write(f'Seed {hi} {first} vs Seed {lo} {second}')
            st.info('Verified conference-specific championship brackets and tiebreak rules can be added separately; these generic pairings do not claim to reproduce any conference’s actual championship.')
        st.markdown('### Conference team power rankings')
        st.caption('Teams are ordered by Courtside power rating; this is not a conference win-loss standing.')
        for ix, (_, team) in enumerate(member.iterrows(), start=1):
            a, b, c = st.columns([3, .9, 1.15], vertical_alignment='center')
            with a:
                st.markdown(f'<div class="cc-name">{ix}. {html.escape(str(team["Team"]))}</div>', unsafe_allow_html=True)
            with b:
                st.markdown(f'<div class="cc-number">{_number(team["Current power"])}</div>', unsafe_allow_html=True)
            with c:
                if st.button('View team →', key=f'cc_team_{league}_{team["Team ID"]}', use_container_width=True):
                    st.session_state['v12_team_pick'] = str(team['Team'])
                    st.session_state['courtside_page'] = 'Teams'
                    st.rerun()
            st.divider()
        with st.expander('Conference rating details', expanded=False):
            st.write(f'Median team power: {_number(conference_summary["Median"])}')
            st.write(f'Top-five average power: {_number(conference_summary["Top five"])}')
            st.caption('These values summarize saved ratings for verified Division I member teams.')
        return

    search = st.text_input('Find conference', placeholder='Search conferences…', key='cc_find')
    sort = st.selectbox('Compare by', ['Average team power', 'Top-five power', 'Median team power'], key='cc_sort')
    key = {'Average team power': 'Average', 'Top-five power': 'Top five', 'Median team power': 'Median'}[sort]
    shown = summary[summary['Conference'].astype(str).str.contains(search, case=False, regex=False, na=False)] if search else summary
    shown = shown.sort_values(key, ascending=False).reset_index(drop=True)
    shown['Displayed rank'] = shown.index + 1
    st.caption(f'{len(shown)} conferences · Ranked by {sort.lower()} · D1 teams with saved ratings only')
    for _, item in shown.iterrows():
        c1, c2, c3, c4 = st.columns([.5, 3.1, 1.3, 1.3], vertical_alignment='center')
        with c1:
            st.markdown(f'<div class="cc-number">#{int(item["Displayed rank"])}</div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="cc-name">{html.escape(str(item["Conference"]))}</div>'
                        f'<div class="cc-muted">{int(item["Teams"])} rated D1 teams</div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="cc-number">{_number(item[key])}</div>'
                        f'<div class="cc-muted" style="text-align:right">{html.escape(sort)}</div>', unsafe_allow_html=True)
        with c4:
            if st.button('View teams →', key=f'cc_open_{league}_{item["Conference"]}', use_container_width=True):
                st.session_state['cc_breakdown'] = str(item['Conference'])
                st.rerun()
        st.divider()
    with st.expander('Advanced conference data & download',expanded=False):
        st.dataframe(summary[['Power rank','Conference','Teams','Average','Median','Top five']],hide_index=True,use_container_width=True)
        st.download_button('Download conference power rankings',summary.to_csv(index=False).encode('utf-8'),'courtside_conference_power.csv','text/csv')
        st.caption('Conference power is an unweighted summary of rated teams, not a win-loss standing or official conference ranking. Coverage can affect averages.')

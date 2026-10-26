"""Courtside V101: descriptive, source-aware preseason team snapshot.

No forecast calculations are changed. Optional context file:
 data/preseason_profiles/2026-27_mens.csv or 2026-27_womens.csv
Required fields to display each optional claim: Team ID, Source URL, Verified as of,
and the corresponding data value. The date is metadata, not independent verification.
"""
from __future__ import annotations
from pathlib import Path
from datetime import date
import pandas as pd
import streamlit as st

SEASON = '2026-27'
PRIOR = '2025-26'
FIELDS = {
    'Prior wins': ('Previous-season wins', lambda v: f'{int(float(v))}'),
    'Prior losses': ('Previous-season losses', lambda v: f'{int(float(v))}'),
    'Prior D1 power': ('Previous-season power rating', lambda v: f'{float(v):+.1f}'),
    'Returning minutes %': ('Returning minutes', lambda v: f'{float(v):.1f}%'),
}

def _number(value):
    try:
        x=float(value)
        return None if pd.isna(x) else x
    except (TypeError, ValueError):
        return None

@st.cache_data(ttl=900,show_spinner=False)
def _optional_context(path):
    p=Path(path)
    if not p.is_file(): return pd.DataFrame(), 'No verified preseason context CSV has been supplied.'
    try:
        table=pd.read_csv(p,dtype={'Team ID':str})
        required={'Team ID','Source URL','Verified as of'}
        if not required.issubset(table.columns):
            return pd.DataFrame(), 'Context file is missing required source metadata columns.'
        return table, ''
    except Exception:
        return pd.DataFrame(), 'Could not read the optional context file.'

def render_preseason_profile_v101(*, team_id, division, rating=None, games=None):
    """Render preseason context, using only data already present or explicitly sourced."""
    st.markdown('#### Preseason snapshot · 2026–27')
    st.caption('Previous-season information is descriptive. It does not modify Courtside ratings, lines, or win probabilities.')
    prior_value=_number(rating.get('Preseason rating')) if rating is not None else None
    current_value=_number(rating.get('Current power')) if rating is not None else None
    played=_number(rating.get('Games played')) if rating is not None else None
    a,b,c=st.columns(3)
    a.metric('Saved preseason prior',f'{prior_value:+.1f}' if prior_value is not None else '—',help='The baseline stored in Courtside’s current ratings. Not a verified prior-season final ranking.')
    b.metric('Current power rating',f'{current_value:+.1f}' if current_value is not None else '—')
    c.metric('Games played',str(int(played)) if played is not None else '—')
    if played is not None and played == 0:
        st.info('No completed 2026–27 games yet. Current team strength is largely based on preseason assumptions.')
    elif played is None:
        st.info('Current games-played information is unavailable.')
    if prior_value is not None:
        st.caption('Saved preseason prior is the model’s current-season starting estimate, not necessarily the final 2025–26 on-court rating.')
    division_key='womens' if 'women' in str(division).lower() else 'mens'
    table, warning=_optional_context(f'data/preseason_profiles/{SEASON}_{division_key}.csv')
    if warning:
        st.caption('Historical record / returning production: '+warning)
        return
    matched=table[table['Team ID'].astype(str)==str(team_id)]
    if matched.empty:
        st.caption('Historical record / returning production: no sourced entry for this team.')
        return
    if len(matched)>1:
        st.warning('Multiple context rows found for this team; source ambiguity prevents display.')
        return
    record=matched.iloc[0]
    url=str(record.get('Source URL') or '').strip()
    asof=pd.to_datetime(record.get('Verified as of'),errors='coerce')
    if not url.startswith(('https://','http://')) or pd.isna(asof) or asof.date()>date.today():
        st.warning('Context row has missing, invalid, or future-dated source metadata; optional claims are hidden.')
        return
    cols=[]
    for field,(label,fmt) in FIELDS.items():
        if field not in record:continue
        v=_number(record[field])
        if v is None:continue
        if field=='Returning minutes %' and not (0<=v<=100):continue
        if field in ('Prior wins','Prior losses') and not (0<=v<=50 and v.is_integer()):continue
        try: cols.append((label,fmt(v)))
        except (ValueError,TypeError):pass
    if not cols:
        st.caption('No usable optional prior-season values are available.')
        return
    st.markdown('**Sourced prior-season context**')
    columns=st.columns(min(3,len(cols)))
    for i,(label,value) in enumerate(cols):columns[i%len(columns)].metric(label,value)
    st.caption(f'Source metadata dated {asof.date().isoformat()}; user-supplied and not independently verified by Courtside.')
    st.markdown(f'[Open supporting source]({url})')

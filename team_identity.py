"""Courtside optional team identification. External logos require appropriate rights."""
from __future__ import annotations
import html
import re
import streamlit as st

PALETTE = ('#24364c', '#8a2736', '#1d5963', '#544779', '#735328')

def _safe_id(team_id):
    value = str(team_id).strip()
    return value if re.fullmatch(r'[0-9]{1,8}', value) else None

def short_name(name):
    name = str(name)
    return ' '.join(name.split()[:2]) if len(name) > 28 else name

def logo_uri(team_id, league):
    """ESPN-hosted logo endpoint. URL access is not a usage license."""
    tid = _safe_id(team_id)
    if not tid: return None
    # ESPN uses the same school athletics logos for its men's and women's listings.
    return f'https://a.espncdn.com/i/teamlogos/ncaa/500/{tid}.png'

def team_identity(col, name, team_id, league, *, external_logos=False):
    with col:
        uri = logo_uri(team_id, league) if external_logos else None
        if uri:
            try:
                st.image(uri, width=78)
            except Exception:
                _initials(name,team_id)
        else:
            _initials(name,team_id)
        st.markdown(f'<div style="font-weight:650;color:#23354B;font-size:1rem;margin-top:7px">{html.escape(str(name))}</div>', unsafe_allow_html=True)

def _initials(name, team_id):
    parts = [x[0] for x in str(name).split()[:3] if x]
    initials=''.join(parts).upper() or 'TEAM'
    idx=sum(ord(c) for c in str(team_id)) % len(PALETTE)
    st.markdown(f'<div style="display:inline-flex;align-items:center;justify-content:center;width:76px;height:76px;border-radius:14px;background:{PALETTE[idx]};color:white;font-weight:750;font-size:22px">{html.escape(initials)}</div>',unsafe_allow_html=True)

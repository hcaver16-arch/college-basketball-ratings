"""Read saved experimental efficiency snapshots; no live all-team API fanout."""
from __future__ import annotations
from pathlib import Path
import math
import pandas as pd
import streamlit as st

@st.cache_data(ttl=900, show_spinner=False)
def _read(sport):
    sport = 'womens-college-basketball' if 'women' in str(sport).lower() else 'mens-college-basketball'
    path = Path('data/efficiency') / f'{sport}_adjusted_latest.csv'
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype={'Team ID':str})
    except (OSError, ValueError):
        return pd.DataFrame()


def merge_team_stats(raw, team_id, league, *, before=None):
    """Experimental adjusted metrics only for current team views.

    For historical/pregame matchups, DO NOT attach a latest snapshot: it would
    leak future games. A dated point-in-time snapshot archive is required first.
    """
    if before is not None:
        return raw
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return raw
    tab = _read(league)
    if tab.empty:
        return raw
    row = tab.loc[tab['Team ID'].astype(str)==str(team_id)]
    if row.empty:
        return raw
    rec=row.iloc[0]
    result=dict(raw)
    if not result.get('validated'):
        return result
    for src, dest in [('adj_o','adj_o'),('adj_d','adj_d'),('adj_em','adj_em')]:
        try:
            val=float(rec[src])
            if math.isfinite(val):
                result[dest]=val
        except (ValueError, TypeError, KeyError):
            pass
    result['adjusted_method']=rec.get('method','')
    result['adjusted_games']=rec.get('games_used',0)
    result['adjusted_snapshot']=rec.get('Snapshot UTC','')
    return result

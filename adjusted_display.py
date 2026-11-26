"""Read saved experimental efficiency snapshots; no live all-team API fanout."""
from __future__ import annotations
from pathlib import Path
import math
import pandas as pd
import streamlit as st

def select_snapshot(paths, before=None):
    """Select a whole verified snapshot strictly before the cutoff."""
    cutoff = pd.to_datetime(before, utc=True, errors='coerce') if before is not None else None
    if before is not None and pd.isna(cutoff):
        return pd.DataFrame()
    best, best_time = pd.DataFrame(), None
    for path in paths:
        try:
            tab = pd.read_csv(path, dtype={'Team ID': str})
            stamps = pd.to_datetime(tab['Snapshot UTC'], utc=True, errors='coerce')
            if tab.empty or stamps.isna().any() or stamps.nunique() != 1:
                continue
            stamp = stamps.iloc[0]
            if cutoff is not None and stamp >= cutoff:
                continue
            if best_time is None or stamp > best_time:
                best, best_time = tab, stamp
        except (OSError, ValueError, KeyError):
            continue
    return best


@st.cache_data(ttl=900, show_spinner=False)
def _read(sport, before=None):
    sport = 'womens-college-basketball' if 'women' in str(sport).lower() else 'mens-college-basketball'
    path = Path('data/efficiency') / f'{sport}_adjusted_latest.csv'
    paths = [path, *sorted((path.parent / 'snapshots' / sport).glob('*.csv'))]
    return select_snapshot(paths, before)


def merge_team_stats(raw, team_id, league, *, before=None):
    """Attach only a verified snapshot strictly preceding a supplied cutoff."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return raw
    tab = _read(league, before)
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

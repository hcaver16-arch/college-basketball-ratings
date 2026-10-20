"""Experimental roster scouting; not trained/validated rating impacts."""
from __future__ import annotations
import pandas as pd


def experimental_roster_signal(summary, incoming):
    """Conservative relative descriptive signals; NOT points or predictive estimate.

    Returns dimensions for comparison only. Missing evidence stays missing.
    """
    if summary is None or summary.empty:
        return {'Status': 'Unavailable — returning production not calculated'}
    s=summary.iloc[0]
    coverage=float(s.get('Player stat coverage %', 0) or 0)
    minutes=pd.to_numeric(s.get('Returning minutes % (known only)'),errors='coerce')
    if pd.isna(minutes):
        return {'Status':'Unavailable — no valid returning minutes total'}
    evidence=incoming if incoming is not None else pd.DataFrame()
    matched=0
    known_transfer_minutes=0.0
    unknown=0
    if not evidence.empty:
        potential=evidence['Status'].astype(str).str.startswith('Potential transfer')
        matched=int(potential.sum())
        known_transfer_minutes=float(pd.to_numeric(evidence.loc[potential,'Previous minutes'],errors='coerce').fillna(0).sum())
        unknown=int((~potential).sum())
    return {
        'Status':'Experimental descriptors only — not fitted or validated',
        'Returning minutes % (documented)':round(float(minutes),1),
        'Prior roster stat coverage %':round(coverage,1),
        'Potential transfers with previous-school IDs':matched,
        'Documented previous-school transfer minutes':round(known_transfer_minutes),
        'Unresolved incoming players':unknown,
        'Reliability':'Review required' if coverage<95 or unknown else 'Roster completeness still unverified',
    }


def illustrative_sensitivity(base_rating, return_pct, transfer_minutes, retained_weight=0.75, added_weight=0.25):
    """What-if visualization ONLY, not a predicted player-adjusted rating.

    Built to avoid silently assigning a meaningful point scale to roster summaries.
    """
    if return_pct is None or pd.isna(return_pct): return None
    baseline=float(base_rating)
    return {'Baseline team rating':baseline,
            'Returning minutes':float(return_pct),
            'Incoming minutes':float(transfer_minutes),
            'Forecast':'Not produced: coefficients require multi-season archived backtesting'}

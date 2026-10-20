"""Exploratory roster retention sensitivity: NOT a calibrated rating model.

No historical player-impact coefficients are estimated here. Retention % is a
fraction of documented prior production and does not establish true roster value.
"""
from __future__ import annotations
import math
import pandas as pd


def roster_sensitivity(base_rating, returning_minutes_pct, reference_retention_pct=50.0,
                       points_per_10pct=0.5):
    """Return clearly labeled what-if scenario; NOT a point spread or forecast."""
    try:
        baseline=float(base_rating)
        retention=float(returning_minutes_pct)
        reference=float(reference_retention_pct)
        slope=float(points_per_10pct)
    except (TypeError, ValueError):
        return None
    if not all(map(math.isfinite,(baseline,retention,reference,slope))):return None
    if not (0 <= retention <= 100 and 0 <= reference <= 100 and 0 <= slope <= 3):return None
    raw=(retention-reference)/10.0*slope
    delta=max(-6.0,min(6.0,raw))
    return {"Historical team baseline":round(baseline,2),
            "Documented returning minutes %":round(retention,1),
            "Reference returning minutes %":round(reference,1),
            "Assumed points per 10 percentage points":round(slope,2),
            "Hypothetical change (pts)":round(delta,2),
            "Hypothetical rating (NOT validated)":round(baseline+delta,2)}


def roster_quality(remaining_roster_row, incoming, minimum_coverage=95):
    """Cautious readiness: never calls any source independently complete."""
    if remaining_roster_row is None: return {"status":"Unavailable", "message":"No documented returning-production summary"}
    s=remaining_roster_row if isinstance(remaining_roster_row,dict) else remaining_roster_row.to_dict()
    try:
        matched=int(s.get('Prior roster players with stats',0) or 0)
        total=int(s.get('Prior roster entries',0) or 0)
    except (ValueError,TypeError):matched,total=0,0
    pct=100*matched/total if total else 0
    if incoming is None or incoming.empty:unknown=None
    elif 'Status' in incoming:unknown=int((~incoming['Status'].fillna('').astype(str).str.startswith('Potential transfer')).sum())
    else:unknown=None
    message=[]
    if not total:message.append('Historical roster unavailable')
    elif pct<minimum_coverage:message.append(f'Only {matched}/{total} historical roster players have totals')
    if unknown is None:message.append('Incoming player origins not evaluated')
    elif unknown:message.append(f'{unknown} incoming player origins unresolved')
    message.append('Independent season and roster completeness not verified')
    return {"status":"Review required", "known_player_coverage_pct":round(pct,1),
            "unresolved_incoming_players":unknown, "message":"; ".join(message)}

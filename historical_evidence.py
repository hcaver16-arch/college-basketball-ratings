"""Conservative dated membership evidence audit for historical research.

No URLs are fetched or authenticated. Manual review is explicit and never
inferred from matching names, later rosters, or post-cutoff box scores.
"""
from __future__ import annotations
import pandas as pd

CUTOFF = pd.Timestamp('2025-11-01',tz='UTC')
EVIDENCE_FIELDS = ['Team ID','Player ID','Source URL','Evidence date','Evidence description','Manual review','Reviewer note']


def classify_evidence(evidence: pd.DataFrame, *, cutoff=CUTOFF) -> pd.DataFrame:
    """Audit user-supplied evidence. Review ≠ independent verification by app."""
    if evidence is None or evidence.empty:
        return pd.DataFrame(columns=EVIDENCE_FIELDS+['Evidence classification','Eligible for point-in-time feature'])
    df=evidence.copy()
    for c in EVIDENCE_FIELDS:
        if c not in df.columns:df[c]=''
    df['Team ID']=df['Team ID'].astype('string').str.strip()
    df['Player ID']=df['Player ID'].astype('string').str.strip()
    urls=df['Source URL'].fillna('').astype(str).str.strip()
    valid_url=urls.str.match(r'^https?://[^\s/]+(?:/[^\s]*)?$',na=False)
    dates=pd.to_datetime(df['Evidence date'],errors='coerce',utc=True)
    review=df['Manual review'].fillna('').astype(str).str.strip().str.lower()
    note=df['Reviewer note'].fillna('').astype(str).str.strip()
    reviewed=review.eq('confirmed') & note.ne('')
    ids=df['Team ID'].notna() & df['Player ID'].notna() & df['Team ID'].ne('') & df['Player ID'].ne('')
    before=dates.notna() & dates.lt(cutoff)
    eligible=ids & before & valid_url & reviewed
    status=[]
    for i in range(len(df)):
        if not ids.iloc[i]:s='Unverified — team/player ID missing'
        elif not valid_url.iloc[i]:s='Unverified — invalid source URL'
        elif pd.isna(dates.iloc[i]):s='Unverified — missing or invalid evidence date'
        elif not before.iloc[i]:s='Retrospective — source dated on/after cutoff'
        elif not reviewed.iloc[i]:s='Pre-cutoff source — manual verification pending'
        else:s='Preseason-confirmed (user-reviewed source; not independently authenticated)'
        status.append(s)
    df['Evidence classification']=status
    df['Eligible for point-in-time feature']=eligible.astype(bool)
    return df


def player_membership_audit(historical_players: pd.DataFrame, verified_evidence: pd.DataFrame) -> pd.DataFrame:
    """Join verified membership to prior player production without look-ahead.

    For the 2025-26 target team, 'Reconstruction team' is the prior team whose
    2024-25 totals were fetched; only same-team rows can contribute to a
    returning-player calculation. No cross-school assumption is made.
    """
    if historical_players is None or historical_players.empty:
        return pd.DataFrame(columns=['Team ID','Player ID','Player','Evidence classification','Returning-production eligible'])
    p=historical_players.copy()
    if 'Team ID' not in p.columns or 'Player ID' not in p.columns:
        return pd.DataFrame(columns=['Evidence classification','Returning-production eligible'])
    p['Team ID']=p['Team ID'].astype('string').str.strip()
    p['Player ID']=p['Player ID'].astype('string').str.strip()
    keys=set()
    if verified_evidence is not None and not verified_evidence.empty and 'Eligible for point-in-time feature' in verified_evidence:
        verified=verified_evidence.loc[verified_evidence['Eligible for point-in-time feature'].fillna(False)]
        keys=set(zip(verified['Team ID'].astype(str),verified['Player ID'].astype(str)))
    matched=[(str(t),str(pid)) in keys for t,pid in zip(p['Team ID'],p['Player ID'])]
    p['Pre-cutoff membership reviewed']=matched
    p['Evidence classification']=['Preseason-confirmed (user-reviewed source)' if yes else 'Retrospectively inferred or unverified' for yes in matched]
    p['Returning-production eligible']=matched
    return p

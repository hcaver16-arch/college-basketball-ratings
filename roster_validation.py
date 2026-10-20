"""Descriptive roster feature audit; deliberately not an inferred point-spread model."""
import pandas as pd
import numpy as np

FEATURES=['Returning minutes % (known only)','Returning points % (known only)',
          'Returning rebounds % (known only)','Returning assists % (known only)']

def _ids(frame):
    return set(frame['Team ID'].dropna().astype(str)) if isinstance(frame,pd.DataFrame) and 'Team ID' in frame else set()

def validate_archive(previous,current,stats,status):
    """Row-level checks and per-school data-availability audit. No claim of complete seasons."""
    schools=sorted(_ids(previous)|_ids(current)|_ids(stats)|_ids(status))
    records=[]
    for tid in schools:
        a=previous[previous['Team ID'].astype(str)==tid] if tid in _ids(previous) else pd.DataFrame()
        b=current[current['Team ID'].astype(str)==tid] if tid in _ids(current) else pd.DataFrame()
        s=stats[stats['Team ID'].astype(str)==tid] if tid in _ids(stats) else pd.DataFrame()
        old_ids=set(a['Player ID'].dropna().astype(str)) if 'Player ID' in a else set()
        new_ids=set(b['Player ID'].dropna().astype(str)) if 'Player ID' in b else set()
        stat_ids=set(s['Player ID'].dropna().astype(str)) if 'Player ID' in s else set()
        duplicates=sum(a['Player ID'].dropna().astype(str).duplicated()) if 'Player ID' in a else 0
        duplicates+=sum(b['Player ID'].dropna().astype(str).duplicated()) if 'Player ID' in b else 0
        labels=[]
        if not old_ids or not new_ids:labels.append('Missing roster')
        if not stat_ids:labels.append('Missing player totals')
        if duplicates:labels.append('Duplicate player IDs')
        if old_ids and stat_ids and len(old_ids&stat_ids)<len(old_ids): labels.append('Player totals incomplete for prior roster')
        if old_ids==new_ids and old_ids:labels.append('Identical season snapshots — verify')
        records.append({'Team ID':tid,'Prior roster players':len(old_ids),
                        'Current roster players':len(new_ids),'Prior players with totals':len(old_ids&stat_ids),
                        'Prior player match %':round(100*len(old_ids&stat_ids)/len(old_ids),1) if old_ids else np.nan,
                        'Returning matched players':len(old_ids&new_ids),'Unmatched arrivals':len(new_ids-old_ids),
                        'Coverage status':'Review: '+', '.join(labels) if labels else 'Available; season completeness unverified'})
    return pd.DataFrame(records)

def model_feature_table(previous,current,stats,status,returning_callback):
    """Join documented retention percentages to roster audit; exclude incomplete cases from fitting."""
    audit=validate_archive(previous,current,stats,status)
    if audit.empty:return audit
    rows=[]
    for tid in audit['Team ID']:
        a=previous[previous['Team ID'].astype(str)==tid] if tid in _ids(previous) else pd.DataFrame()
        b=current[current['Team ID'].astype(str)==tid] if tid in _ids(current) else pd.DataFrame()
        s=stats[stats['Team ID'].astype(str)==tid] if tid in _ids(stats) else pd.DataFrame()
        r={'Team ID':tid}
        if not a.empty and not b.empty and not s.empty:
            try:
                summary,_,_=returning_callback(pd.concat([a,b],ignore_index=True),s)
                if not summary.empty:
                    line=summary.iloc[0]
                    r.update({k:pd.to_numeric(line.get(k),errors='coerce') for k in FEATURES})
            except (ValueError,KeyError,TypeError,IndexError):pass
        rows.append(r)
    result=audit.merge(pd.DataFrame(rows),on='Team ID',how='left')
    result['Usable for exploratory features']=(result['Prior player match %']>=95)&result[FEATURES[0]].notna()&(~result['Coverage status'].str.contains('Duplicate|Identical|Missing roster',regex=True))
    return result

def backtest_readiness(frame,season):
    if frame.empty:return 'No stored player evidence yet.'
    eligible=int(frame['Usable for exploratory features'].sum())
    return (f'{eligible} of {len(frame)} archived teams have usable descriptive returning-production features. '
            f'These are for {season}; they cannot be used to backtest November 2025 without pre-November-2025 roster snapshots and 2024–25 player totals.')

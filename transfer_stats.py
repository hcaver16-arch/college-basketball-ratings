"""Targeted previous-school box score retrieval for provisional transfer candidates.

No numerical player impacts or transfer confirmations are inferred. Results are
sourced to ESPN boxscore aggregates, with game coverage reported separately.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from player_stats_import import fetch_prior_stats

COLUMNS = ['Team ID','Player ID','Minutes','Points','Rebounds','Assists','Source']

def previous_school_targets(candidates):
    if candidates is None or candidates.empty:
        return pd.DataFrame(columns=['Team ID','Team'])
    c = candidates.copy()
    c = c[c['Status'].astype(str).str.startswith('Potential transfer')]
    c = c[c['Prior school ID'].notna() & c['Prior school'].notna()]
    c = c[c['Prior school ID'].astype(str).str.strip().ne('')]
    if c.empty:
        return pd.DataFrame(columns=['Team ID','Team'])
    return (c[['Prior school ID','Prior school']].rename(columns={'Prior school ID':'Team ID','Prior school':'Team'})
            .assign(**{'Team ID':lambda x:x['Team ID'].astype(str)})
            .drop_duplicates('Team ID').reset_index(drop=True))

def retrieve_previous_school_stats(sport, candidates, progress=None, max_schools=30):
    """Returns stats, per-school diagnostics, warnings and attempted school count.

    Only identified previous schools are queried. A bounded number is intentional
    to avoid making hundreds of calls on an interactive free hosting instance.
    """
    targets=previous_school_targets(candidates)
    if len(targets)>max_schools:
        return pd.DataFrame(columns=COLUMNS),pd.DataFrame(),[f'{len(targets)} schools exceed batch limit {max_schools}; narrow the roster audit to fewer destination schools.'],0
    pieces=[];diagnostics=[];warnings=[]
    for i,(_,school) in enumerate(targets.iterrows(),1):
        sub=pd.DataFrame([school])
        try:
            stats,diag,errors=fetch_prior_stats(sport,sub,season=2026,max_games=45,max_workers=4)
            if not stats.empty:pieces.append(stats)
            if not diag.empty:diagnostics.append(diag)
            warnings.extend(errors)
        except Exception as exc:
            warnings.append(f'{school["Team"]}: {type(exc).__name__} — {str(exc)[:130]}')
        if progress:progress(i,len(targets))
    total=pd.concat(pieces,ignore_index=True).drop_duplicates(['Team ID','Player ID']) if pieces else pd.DataFrame(columns=COLUMNS)
    details=pd.concat(diagnostics,ignore_index=True) if diagnostics else pd.DataFrame()
    return total,details,warnings,len(targets)

def transfer_coverage(candidates, statistics, diagnostics):
    """Player-level matching audit; no missing totals are substituted with zero."""
    selected=candidates[candidates['Status'].astype(str).str.startswith('Potential transfer')].copy()
    if selected.empty:return pd.DataFrame(columns=['Player','Prior school','Statistics matched','Boxscore coverage'])
    lookup=set()
    if statistics is not None and not statistics.empty:
        lookup=set(zip(statistics['Team ID'].astype(str),statistics['Player ID'].astype(str)))
    coverage={}
    if diagnostics is not None and not diagnostics.empty:
        coverage=dict(zip(diagnostics['Team'].astype(str),diagnostics['Coverage'].astype(str)))
    return pd.DataFrame([{'Player':r['Player'],'Prior school':r['Prior school'],
                          'Statistics matched':(str(r['Prior school ID']),str(r['Player ID'])) in lookup,
                          'Boxscore coverage':coverage.get(str(r['Prior school']),'Not retrieved')}
                         for _,r in selected.iterrows()])

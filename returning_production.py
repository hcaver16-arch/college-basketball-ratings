"""Conservative returning production analysis from season-labeled roster snapshots and sourced stats."""
from __future__ import annotations
import pandas as pd

STATS_COLUMNS = ['Team ID','Player ID','Minutes','Points','Rebounds','Assists','Source']
MEASURES = ['Minutes','Points','Rebounds','Assists']

def calculate_returning_production(snapshots: pd.DataFrame, stats: pd.DataFrame, previous_season=2026, current_season=2027):
    """Return (summary, player_audit, warnings). Never infer missing players as confirmed departures."""
    warnings=[]
    if snapshots is None or snapshots.empty:
        return pd.DataFrame(), pd.DataFrame(), ['No roster snapshots are loaded.']
    if stats is None or stats.empty:
        return pd.DataFrame(), pd.DataFrame(), ['Upload prior-season player totals before calculating returning production. No production values were assumed.']
    required = {'Team ID','Player ID',*MEASURES,'Source'}
    missing=required-set(stats.columns)
    if missing: return pd.DataFrame(),pd.DataFrame(),['Statistics file missing columns: '+', '.join(sorted(missing))]
    stats=stats.copy()
    stats['Team ID']=stats['Team ID'].astype(str).str.strip()
    stats['Player ID']=stats['Player ID'].astype(str).str.strip()
    for m in MEASURES: stats[m]=pd.to_numeric(stats[m],errors='coerce')
    stats['Source']=stats['Source'].fillna('').astype(str).str.strip()
    invalid=(stats[MEASURES].isna().any(axis=1)|stats[MEASURES].lt(0).any(axis=1)|(stats['Source']=='')|
             stats['Team ID'].eq('')|stats['Player ID'].eq(''))
    if invalid.any(): warnings.append(f'{int(invalid.sum())} statistics rows were excluded for missing source, identity or nonnegative numeric totals.')
    stats=stats.loc[~invalid].drop_duplicates(['Team ID','Player ID'],keep=False)
    if stats.empty: return pd.DataFrame(),pd.DataFrame(),warnings+['No valid sourced player statistics remain.']
    snaps=snapshots.copy()
    snaps['Team ID']=snaps['Team ID'].astype(str)
    snaps['Player ID']=snaps['Player ID'].astype(str)
    results=[]; audits=[]
    for tid,team_rows in snaps.groupby('Team ID'):
        old=team_rows[team_rows['Roster season']==previous_season].drop_duplicates('Player ID')
        new=team_rows[team_rows['Roster season']==current_season].drop_duplicates('Player ID')
        if old.empty or new.empty:
            warnings.append(f'{team_rows["Team"].iloc[0]}: missing a roster season; skipped.')
            continue
        if set(old['Player ID'])==set(new['Player ID']):
            warnings.append(f'{team_rows["Team"].iloc[0]}: identical roster IDs across seasons; skipped as potentially stale.')
            continue
        oldstats=stats[stats['Team ID']==tid]
        matched=old[['Team ID','Team','Player ID','Player']].merge(oldstats,on=['Team ID','Player ID'],how='left',indicator=True)
        matched['On current roster snapshot']=matched['Player ID'].isin(set(new['Player ID']))
        matched['Has valid statistics']=matched['_merge'].eq('both')
        matched=matched.drop(columns='_merge')
        audits.append(matched)
        coverage=len(oldstats[oldstats['Player ID'].isin(old['Player ID'])].drop_duplicates('Player ID'))/len(old)
        row={'Team':old['Team'].iloc[0],'Team ID':tid,'Prior roster entries':len(old),
             'Current roster entries':len(new),'Prior roster players with stats':int(matched['Has valid statistics'].sum()),
             'Player stat coverage %':round(100*coverage,1),'Confidence':'Incomplete roster verification'}
        for m in MEASURES:
            known=matched[matched['Has valid statistics']]
            total=known[m].sum()
            returning=known.loc[known['On current roster snapshot'],m].sum()
            row[f'Known {m.lower()}']=round(float(total),1)
            row[f'Returning {m.lower()}']=round(float(returning),1)
            row[f'Returning {m.lower()} % (known only)']=round(100*returning/total,1) if total>0 else None
        row['Confidence']=('Tentative — reconcile roster completeness' if coverage>=0.95 else 'Low — missing prior-season player stats')
        results.append(row)
    return pd.DataFrame(results),pd.concat(audits,ignore_index=True) if audits else pd.DataFrame(),warnings

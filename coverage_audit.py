"""Read-only completeness checks. Do not infer missing player or team totals."""
import pandas as pd

def audit_coverage(previous,current,stats,status):
    if status.empty or 'Team ID' not in status:return pd.DataFrame()
    rows=[]
    for _,r in status.iterrows():
        tid=str(r['Team ID'])
        a=previous.loc[previous['Team ID'].astype(str).eq(tid)] if 'Team ID' in previous else pd.DataFrame()
        b=current.loc[current['Team ID'].astype(str).eq(tid)] if 'Team ID' in current else pd.DataFrame()
        s=stats.loc[stats['Team ID'].astype(str).eq(tid)] if 'Team ID' in stats else pd.DataFrame()
        roster=set(a['Player ID'].dropna().astype(str)) if 'Player ID' in a else set()
        stat_ids=set(s['Player ID'].dropna().astype(str)) if 'Player ID' in s else set()
        completed=pd.to_numeric(r.get('Completed games in feed'),errors='coerce')
        parsed=pd.to_numeric(r.get('Game box scores parsed'),errors='coerce')
        game_cov=round(parsed/completed*100,1) if pd.notna(completed) and completed>0 and pd.notna(parsed) else None
        issues=[]
        if a.empty or b.empty:issues.append('Missing roster snapshot')
        if not stat_ids:issues.append('Missing player totals')
        if roster and stat_ids-roster:issues.append(f'{len(stat_ids-roster)} box-score players absent from prior roster')
        if roster and roster-stat_ids:issues.append(f'{len(roster-stat_ids)} prior roster players without box-score totals')
        if game_cov is not None and game_cov<100:issues.append('Unparsed games; automatic retry eligible')
        if game_cov is None:issues.append('Game counts not recorded; rerun collector')
        if roster and 'Player ID' in b and roster==set(b['Player ID'].dropna().astype(str)):issues.append('Identical snapshots; review')
        rows.append({'Team ID':tid,'Team':r.get('Team',tid),'Collector state':r.get('state','unknown'),
          'Discovered completed games':completed,'Parsed game box scores':parsed,'Box-score coverage %':game_cov,
          'Prior roster IDs':len(roster),'Player IDs in totals':len(stat_ids),
          'Stats athletes absent from roster':len(stat_ids-roster),'Roster athletes without totals':len(roster-stat_ids),
          'Review reasons':'; '.join(issues) if issues else 'No structural issues detected; season still unverified'})
    return pd.DataFrame(rows)

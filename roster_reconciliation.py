"""Provenance-aware prior-season player pool from season roster + box-score totals.

Not an official roster, not proof of enrollment or season completeness.
"""
import pandas as pd

POOL_COLS = ['Team ID','Team','Player ID','Player','Position','Class','Roster season','Roster source','Evidence source','In roster snapshot','In box-score totals']

def reconcile_prior_players(previous, totals):
    if previous is None: previous = pd.DataFrame()
    if totals is None: totals = pd.DataFrame()
    prior=previous.copy(); stats=totals.copy()
    for frame in (prior,stats):
        for col in ('Team ID','Player ID'):
            if col not in frame: frame[col]=pd.Series(dtype=str)
            frame[col]=frame[col].astype('string').str.strip()
        frame.dropna(subset=['Team ID','Player ID'],inplace=True)
        frame.drop(frame[(frame['Team ID']=='') | (frame['Player ID']=='')].index,inplace=True)
    prior=prior.drop_duplicates(['Team ID','Player ID'],keep='last')
    stats=stats.drop_duplicates(['Team ID','Player ID'],keep='last')
    original=set(zip(prior['Team ID'],prior['Player ID']))
    recorded=set(zip(stats['Team ID'],stats['Player ID']))
    rows=[]
    for _,r in prior.iterrows():
        item=r.to_dict(); k=(r['Team ID'],r['Player ID'])
        item['In roster snapshot']=True
        item['In box-score totals']=k in recorded
        item['Evidence source']='Roster + box score' if k in recorded else 'Roster only'
        rows.append(item)
    team_names=(prior.drop_duplicates('Team ID').set_index('Team ID')['Team'].to_dict() if 'Team' in prior else {})
    for _,r in stats.iterrows():
        k=(r['Team ID'],r['Player ID'])
        if k in original:continue
        source=r.get('Source','')
        rows.append({'Team ID':r['Team ID'],'Team':team_names.get(r['Team ID'],''),
             'Player ID':r['Player ID'],'Player':'Unknown (box-score ID only)',
             'Position':'','Class':'','Roster season':2026,
             'Roster source':'Box-score totals; not a roster snapshot',
             'Evidence source':source if pd.notna(source) and str(source).strip() else 'Box-score totals (source unspecified)',
             'In roster snapshot':False,'In box-score totals':True})
    if not rows:return pd.DataFrame(columns=POOL_COLS)
    out=pd.DataFrame(rows)
    for col in POOL_COLS:
        if col not in out:out[col]=pd.NA
    return out[POOL_COLS].drop_duplicates(['Team ID','Player ID'])

def reconciliation_summary(previous, totals, current):
    pool=reconcile_prior_players(previous,totals)
    if pool.empty:return pd.DataFrame(columns=['Team ID','Roster-only players','Roster + box-score players','Box-score-only players','Documented prior players','Matched on current roster','Documented returning minutes %'])
    stat=totals.copy()
    if 'Team ID' in stat and 'Player ID' in stat:
        stat['Team ID']=stat['Team ID'].astype(str);stat['Player ID']=stat['Player ID'].astype(str)
    current_ids=set(zip(current['Team ID'].astype(str),current['Player ID'].astype(str))) if current is not None and {'Team ID','Player ID'}.issubset(current.columns) else set()
    rows=[]
    for tid,g in pool.groupby('Team ID'):
        keys=set(zip(g['Team ID'].astype(str),g['Player ID'].astype(str)))
        ts=stat[stat['Team ID'].eq(str(tid))] if 'Team ID' in stat else pd.DataFrame()
        if not ts.empty and 'Minutes' in ts:
            minutes=pd.to_numeric(ts['Minutes'],errors='coerce')
            valid=minutes.notna() & minutes.ge(0)
            denom=minutes[valid].sum()
            is_return=ts['Player ID'].astype(str).map(lambda pid:(str(tid),pid) in current_ids)
            pct=round(100*minutes[valid & is_return].sum()/denom,1) if denom>0 else None
        else:pct=None
        rows.append({'Team ID':tid,'Roster-only players':int(((g['In roster snapshot']) & (~g['In box-score totals'])).sum()),
        'Roster + box-score players':int(((g['In roster snapshot']) & (g['In box-score totals'])).sum()),
        'Box-score-only players':int((~g['In roster snapshot'] & g['In box-score totals']).sum()),
        'Documented prior players':len(keys),'Matched on current roster':len(keys & current_ids),
        'Documented returning minutes %':pct})
    return pd.DataFrame(rows)

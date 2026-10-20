"""Evidence-first transfer candidates from audited season-labeled ESPN rosters.

Candidate != confirmed transfer. Previous school requires an actual previous-season
roster ID match; otherwise player origin is unknown. Never change team ratings here.
"""
import pandas as pd

COLS=['Team ID','Team','Player ID','Player','Prior school','Prior school ID','Status','Previous minutes','Previous points','Previous rebounds','Previous assists','Statistics source']

def identify_incoming(snapshots, stats=None, previous_season=2026, current_season=2027):
    if snapshots is None or snapshots.empty:
        return pd.DataFrame(columns=COLS), ['Run the roster audit first.']
    df=snapshots.copy()
    for field in ('Team ID','Player ID'):df[field]=df[field].astype(str).str.strip()
    old=df[df['Roster season']==previous_season].drop_duplicates(['Team ID','Player ID'])
    new=df[df['Roster season']==current_season].drop_duplicates(['Team ID','Player ID'])
    prior_index=old.groupby('Player ID',sort=False)
    result=[];warnings=[]
    if old.empty or new.empty:return pd.DataFrame(columns=COLS), ['Missing season-labeled rosters.']
    verified=set()
    for tid,g in df.groupby('Team ID'):
        a=set(g.loc[g['Roster season']==previous_season,'Player ID'])
        b=set(g.loc[g['Roster season']==current_season,'Player ID'])
        if a and b and a!=b:verified.add(tid)
        else:warnings.append(f'{g["Team"].iloc[0]}: one season missing or identical; incoming classification withheld.')
    available_stats=pd.DataFrame()
    if stats is not None and not stats.empty:
        available_stats=stats.copy()
        for field in ('Team ID','Player ID'):available_stats[field]=available_stats[field].astype(str).str.strip()
    for _,p in new.iterrows():
        tid=p['Team ID'];pid=p['Player ID']
        if tid not in verified:continue
        if (old['Team ID'].eq(tid)&old['Player ID'].eq(pid)).any():continue
        prior=prior_index.get_group(pid) if pid in prior_index.groups else pd.DataFrame()
        other=prior[prior['Team ID']!=tid] if not prior.empty else pd.DataFrame()
        row={'Team ID':tid,'Team':p['Team'],'Player ID':pid,'Player':p['Player'],
             'Prior school':'Unknown','Prior school ID':'','Status':'New roster appearance — origin unknown',
             'Previous minutes':None,'Previous points':None,'Previous rebounds':None,'Previous assists':None,'Statistics source':''}
        if len(other)==1:
            q=other.iloc[0]
            row.update({'Prior school':q['Team'],'Prior school ID':q['Team ID'],
                        'Status':'Possible transfer — prior school matched in audited rosters'})
            if not available_stats.empty:
                found=available_stats[available_stats['Team ID'].eq(q['Team ID'])&available_stats['Player ID'].eq(pid)]
                if len(found)==1:
                    s=found.iloc[0]
                    for metric in ('Minutes','Points','Rebounds','Assists'):
                        row['Previous '+metric.lower()]=pd.to_numeric(s.get(metric),errors='coerce')
                    row['Statistics source']=str(s.get('Source') or '')
        elif len(other)>1:
            row['Status']='Ambiguous prior school — multiple roster matches'
        result.append(row)
    return pd.DataFrame(result,columns=COLS), warnings + ['Prior-school detection only covers schools selected in the roster audit. Unmatched origins can be freshmen, transfers or incomplete data. All matches are provisional.']

"""Opt-in 2025-26 D1 prior-roster lookup; matches stable provider player IDs.

Not a transfer registry: coverage, player histories and provider season semantics
must be independently checked before claims of confirmed transfers.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from roster_tracking import read_roster

RESULT_COLUMNS = ['Team ID','Team','Player ID','Player','Prior school','Prior school ID','Status',
                  'Previous minutes','Previous points','Previous rebounds','Previous assists','Statistics source']

def scan_previous_rosters(sport, directory, progress=None, max_workers=8):
    schools=directory[['Team ID','Team']].dropna().copy()
    schools['Team ID']=schools['Team ID'].astype(str)
    schools=schools.drop_duplicates('Team ID')
    pieces=[];failed=[];count=len(schools)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        tasks={executor.submit(read_roster,sport,str(t['Team ID']),str(t['Team']),2026):
               (str(t['Team ID']),str(t['Team'])) for _,t in schools.iterrows()}
        for i,future in enumerate(as_completed(tasks),1):
            tid,name=tasks[future]
            try:
                result=future.result()
                if result.empty: failed.append({'Team ID':tid,'Team':name,'Issue':'Empty historical roster'})
                else: pieces.append(result)
            except Exception as err:
                failed.append({'Team ID':tid,'Team':name,'Issue':str(err)[:120]})
            if progress and (i%8==0 or i==count):progress(i,count)
    roster=pd.concat(pieces,ignore_index=True) if pieces else pd.DataFrame(columns=['Team ID','Team','Player ID','Roster season'])
    return roster, pd.DataFrame(failed,columns=['Team ID','Team','Issue']),count

def match_candidates(candidates, history, stats=None):
    if candidates is None or candidates.empty: return pd.DataFrame(columns=RESULT_COLUMNS)
    result=candidates.copy()
    for c in RESULT_COLUMNS:
        if c not in result:result[c]=None
    if history is None or history.empty:return result[RESULT_COLUMNS]
    old=history.copy()
    old['Player ID']=old['Player ID'].astype(str).str.strip()
    old['Team ID']=old['Team ID'].astype(str).str.strip()
    grouped={pid:g[['Team ID','Team']].drop_duplicates('Team ID') for pid,g in old.groupby('Player ID')}
    stat_rows={}
    if stats is not None and not stats.empty:
        s=stats.copy()
        s['Player ID']=s['Player ID'].astype(str).str.strip()
        s['Team ID']=s['Team ID'].astype(str).str.strip()
        stat_rows={(r['Team ID'],r['Player ID']):r for _,r in s.iterrows()}
    for i,row in result.iterrows():
        pid=str(row['Player ID']).strip(); tid=str(row['Team ID']).strip()
        possible=grouped.get(pid)
        if possible is None:continue
        other=possible[possible['Team ID']!=tid]
        if len(other)==1:
            match=other.iloc[0]
            result.at[i,'Prior school']=match['Team']
            result.at[i,'Prior school ID']=match['Team ID']
            result.at[i,'Status']='Potential transfer — prior D1 roster ID match (verify)'
            stat=stat_rows.get((match['Team ID'],pid))
            if stat is not None:
                for col in ['Minutes','Points','Rebounds','Assists']:
                    result.at[i,'Previous '+col.lower()]=pd.to_numeric(stat.get(col),errors='coerce')
                result.at[i,'Statistics source']=str(stat.get('Source') or '')
        elif len(other)>1:
            result.at[i,'Status']='Ambiguous match — multiple prior D1 schools'
        else:
            result.at[i,'Status']='No different prior D1 roster match — origin unknown'
    return result[RESULT_COLUMNS]

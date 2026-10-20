"""Conservative roster snapshots: compare identity, never infer transfers from missing roster data."""
from __future__ import annotations
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {'User-Agent':'Mozilla/5.0','Accept':'application/json'}
COLUMNS = ['Team ID','Team','Player ID','Player','Position','Class','Roster season','Roster source']

def read_roster(sport, team_id, team_name, season, session=None):
    url=f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/teams/{team_id}/roster'
    http=session or requests
    resp=http.get(url,params={'season':season},headers=HEADERS,timeout=25)
    resp.raise_for_status()
    payload=resp.json()
    athletes=payload.get('athletes') or []
    if isinstance(athletes,dict):
        athletes=[a for group in athletes.values() if isinstance(group,list) for a in group]
    if not isinstance(athletes,list):
        raise ValueError('Roster athletes field has an unexpected format')
    rows=[]
    for item in athletes:
        if not isinstance(item,dict):continue
        player=item.get('athlete',item)
        if not isinstance(player,dict):continue
        pid=str(player.get('id') or '').strip()
        if not pid:continue
        pos=player.get('position') or {}; exp=player.get('experience') or {}
        rows.append({'Team ID':str(team_id),'Team':team_name,'Player ID':pid,'Player':player.get('displayName') or player.get('fullName') or 'Unknown',
                     'Position':pos.get('abbreviation','') if isinstance(pos,dict) else '',
                     'Class':exp.get('displayValue','') if isinstance(exp,dict) else '',
                     'Roster season':season,'Roster source':resp.url})
    return pd.DataFrame(rows,columns=COLUMNS).drop_duplicates(['Team ID','Player ID'])

def compare_snapshots(previous,current):
    """A player's previous team matching by ID is credible only if provider obeys season selector."""
    if previous.empty or current.empty:
        return pd.DataFrame(), 'Insufficient roster snapshots; no returning/transfer classifications made.'
    a=previous.drop_duplicates('Player ID')
    b=current.drop_duplicates('Player ID').copy()
    # A same-ID appearance within the same team is a potential return, never confirmation of eligibility.
    previous_team=a.set_index('Player ID')['Team ID'].to_dict()
    previous_name=a.set_index('Player ID')['Team'].to_dict()
    b['Prior roster team']=b['Player ID'].map(previous_name)
    def status(r):
        old=previous_team.get(r['Player ID'])
        if old is None:return 'Not in prior roster snapshot — origin unknown'
        if old==r['Team ID']:return 'Appears on both roster snapshots'
        return 'Different team in prior snapshot — possible transfer'
    b['Roster comparison']=b.apply(status,axis=1)
    return b, None

def audit_teams(sport, directory, previous_season=2026, current_season=2027, max_teams=12):
    """Manual batch requests only, no automatic impact or bogus roster completeness percentages."""
    teams=directory[['Team ID','Team']].drop_duplicates('Team ID').head(max_teams)
    rows=[]; errors=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(read_roster,sport,str(t['Team ID']),str(t['Team']),season):(str(t['Team ID']),season)
                 for _,t in teams.iterrows() for season in (previous_season,current_season)}
        for f in as_completed(futures):
            tid,season=futures[f]
            try:rows.append(f.result())
            except Exception as exc:errors.append({'Team ID':tid,'Season':season,'Problem':str(exc)[:180]})
    both=pd.concat(rows,ignore_index=True) if rows else pd.DataFrame(columns=COLUMNS)
    return both,pd.DataFrame(errors,columns=['Team ID','Season','Problem'])

def classify_team(snapshots,team_id):
    # ESPN may silently ignore `season` parameter. Require different same-team athlete sets
    # before reporting comparisons. Equal lists are ambiguous, not proof of no transfers.
    x=snapshots[snapshots['Team ID'].astype(str)==str(team_id)]
    old=x[x['Roster season']==2026]; new=x[x['Roster season']==2027]
    if old.empty or new.empty:return pd.DataFrame(),'Missing one or both season snapshots; no roster inference.'
    if set(old['Player ID'])==set(new['Player ID']):
        return pd.DataFrame(),'Prior/current player IDs are identical. Provider may ignore season selector; comparison withheld.'
    # Pairwise team-specific comparison. Cross-team transfer detection requires all D1 rosters.
    comp,_=compare_snapshots(old,new)
    return comp,'Tentative roster comparison only. ESPN season labeling is not independently verified. New names are not automatically labeled transfers.'

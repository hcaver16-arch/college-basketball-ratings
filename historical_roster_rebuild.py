"""Reconstruct 2024-25 player production and 2025-26 memberships.

Retrospective season-labeled rosters are NOT point-in-time preseason snapshots.
Do not use these features in a legitimate November-2025 held-out model without
independent pre-cutoff verification of the roster membership and source dates.
"""
from __future__ import annotations
import pandas as pd
from roster_tracking import read_roster
from player_stats_import import fetch_prior_stats
from roster_reconciliation import reconcile_prior_players

SEASON_STATS = 2025
SEASON_ROSTER = 2026
CUTOFF = '2025-11-01'

def reconstruct_teams(sport, teams, roster_reader=read_roster, stats_reader=fetch_prior_stats):
    """Return per-team diagnostics, features and player evidence (no future claims)."""
    audit=[]; features=[]; players=[]
    for _, t in teams.iterrows():
        tid=str(t['Team ID']); name=str(t['Team'])
        try:
            old=roster_reader(sport,tid,name,SEASON_STATS)
            incoming=roster_reader(sport,tid,name,SEASON_ROSTER)
            totals, diag, errors=stats_reader(sport,pd.DataFrame([{'Team ID':tid,'Team':name}]),season=SEASON_STATS,max_games=45,max_workers=4)
            if old is None: old=pd.DataFrame()
            if incoming is None: incoming=pd.DataFrame()
            if totals is None: totals=pd.DataFrame()
            pool=reconcile_prior_players(old,totals)
            old_ids=set(pool['Player ID'].dropna().astype(str)) if 'Player ID' in pool else set()
            current_ids=set(incoming['Player ID'].dropna().astype(str)) if 'Player ID' in incoming else set()
            stat_ids=set(totals['Player ID'].dropna().astype(str)) if 'Player ID' in totals else set()
            d=diag.iloc[0] if diag is not None and not diag.empty else {}
            completed=pd.to_numeric(d.get('Completed games in feed'),errors='coerce')
            parsed=pd.to_numeric(d.get('Game box scores parsed'),errors='coerce')
            qualified=(pd.notna(completed) and completed>0 and pd.notna(parsed) and parsed==completed and bool(stat_ids) and bool(current_ids))
            result={'Team ID':tid,'Team':name,'Prior player pool':len(old_ids),'2025-26 roster IDs':len(current_ids),'Stat player IDs':len(stat_ids),'Discovered games':completed,'Parsed games':parsed,'Roster only':len(old_ids-stat_ids),'Box-score-only IDs':len(stat_ids-set(old['Player ID'].astype(str))) if 'Player ID' in old else len(stat_ids),'Known as of 2025-11-01':False,'Historical evidence status':'RETROSPECTIVE — 2025-26 roster date not verified','Source errors':'; '.join(map(str,errors[:3])) if errors else ''}
            if not qualified:result['Historical evidence status']='INCOMPLETE — retrieved historical data insufficient'
            audit.append(result)
            if not totals.empty and 'Minutes' in totals:
                s=totals.copy();s['Player ID']=s['Player ID'].astype(str)
                mins=pd.to_numeric(s['Minutes'],errors='coerce')
                mask=mins.notna() & (mins>=0)
                numerator=mins[mask & s['Player ID'].isin(current_ids)].sum()
                denominator=mins[mask].sum()
                returning_pct=float(100*numerator/denominator) if denominator>0 else None
                features.append({'Team ID':tid,'Team':name,'Season target':'2025-26','Returning minutes % (retrospective)':round(returning_pct,2) if returning_pct is not None else None,'Returning player IDs':len(old_ids&current_ids),'Documented prior players':len(old_ids),'Box-score data usable':qualified,'Point-in-time eligible':False,'Eligibility reason':'Roster membership not independently archived before 2025-11-01'})
                s['Current roster ID match']=s['Player ID'].isin(current_ids)
                s['Reconstruction team']=name
                s['Evidence type']='2024-25 game box score'
                players.append(s)
            else:
                features.append({'Team ID':tid,'Team':name,'Season target':'2025-26','Returning minutes % (retrospective)':None,'Returning player IDs':len(old_ids&current_ids),'Documented prior players':len(old_ids),'Box-score data usable':False,'Point-in-time eligible':False,'Eligibility reason':'Missing box-score totals and unverified roster dating'})
        except Exception as exc:
            audit.append({'Team ID':tid,'Team':name,'Historical evidence status':f'ERROR: {type(exc).__name__}: {str(exc)[:140]}','Known as of 2025-11-01':False})
    return pd.DataFrame(audit),pd.DataFrame(features),pd.concat(players,ignore_index=True) if players else pd.DataFrame()


def source_cutoff_audit(upload, team_ids, cutoff=CUTOFF):
    """Dated, sourced team membership evidence; does NOT turn a retrospective metric into a valid pregame feature."""
    required=['Team ID','Player ID','2025-26 team confirmed by','Source URL','Evidence date']
    if upload is None:return pd.DataFrame(columns=required+['Eligible evidence']), 'No independent pre-cutoff evidence uploaded.'
    try: frame=pd.read_csv(upload,dtype={'Team ID':str,'Player ID':str})
    except Exception as exc:return pd.DataFrame(),f'Could not read evidence CSV: {exc}'
    missing=[x for x in required if x not in frame]
    if missing:return frame,'Missing columns: '+', '.join(missing)
    frame=frame.copy()
    dt=pd.to_datetime(frame['Evidence date'],errors='coerce',utc=True)
    cutoff_ts=pd.Timestamp(cutoff,tz='UTC')
    frame['Eligible evidence']=(frame['Team ID'].isin(set(map(str,team_ids))) & frame['Player ID'].notna() & frame['Source URL'].fillna('').astype(str).str.startswith(('http://','https://')) & dt.notna() & dt.lt(cutoff_ts))
    return frame, f"{int(frame['Eligible evidence'].sum())} dated evidence rows passed basic date/URL checks; these are NOT independently authenticated by the app."

"""Courtside V103: source-aware, READ-ONLY roster continuity analysis.

Does not estimate transfer impact or change prediction ratings.
"""
import argparse, json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

SPORTS = ('mens-college-basketball', 'womens-college-basketball')

def load(root, division, kind):
    p = root / f'{division}_{kind}.csv.gz'
    if not p.exists(): return pd.DataFrame()
    df = pd.read_csv(p, dtype={'Team ID':'string','Player ID':'string'}, low_memory=False)
    for col in ('Team ID','Player ID'):
        if col in df: df[col] = df[col].astype('string').str.strip()
    if {'Team ID','Player ID'}.issubset(df.columns):
        df = df.dropna(subset=['Team ID','Player ID'])
        df = df[(df['Team ID']!='') & (df['Player ID']!='')]
        df = df.drop_duplicates(['Team ID','Player ID'], keep='last')
    return df

def column(df, *names):
    mapping={str(c).lower().replace(' ','').replace('_',''):c for c in df.columns}
    for n in names:
        found=mapping.get(n.lower().replace(' ','').replace('_',''))
        if found: return found
    return None

def records(root, division):
    now=load(root,division,'current_rosters')
    old=load(root,division,'previous_rosters')
    stats=load(root,division,'previous_stats')
    status=load(root,division,'collection_status')
    for df in (now,old,stats):
        if not df.empty and not {'Team ID','Player ID'}.issubset(df.columns):
            raise ValueError('Roster archive missing Team ID / Player ID columns')
    team_ids=set()
    for df in (now,old,stats,status):
        if 'Team ID' in df: team_ids.update(df['Team ID'].dropna().astype(str))
    output=[];details=[]
    minutes_key=column(stats,'Minutes','Total Minutes','Minutes Played')
    points_key=column(stats,'Points','PTS')
    rebound_key=column(stats,'Rebounds','REB')
    assist_key=column(stats,'Assists','AST')
    for tid in sorted(team_ids):
        n=now[now['Team ID'].eq(tid)] if 'Team ID' in now else pd.DataFrame()
        p=old[old['Team ID'].eq(tid)] if 'Team ID' in old else pd.DataFrame()
        s=stats[stats['Team ID'].eq(tid)] if 'Team ID' in stats else pd.DataFrame()
        st=status[status['Team ID'].eq(tid)] if 'Team ID' in status else pd.DataFrame()
        info=st.iloc[-1] if len(st) else {}
        name=(str(n.iloc[0]['Team']) if len(n) and 'Team' in n else str(p.iloc[0]['Team']) if len(p) and 'Team' in p else str(info.get('Team',tid)))
        current=set(n['Player ID'].astype(str)) if 'Player ID' in n else set()
        previous=set(p['Player ID'].astype(str)) if 'Player ID' in p else set()
        prior_stats=set(s['Player ID'].astype(str)) if 'Player ID' in s else set()
        returning=current & previous
        known_new=current-previous
        prior_missing=len(p)==0
        coverage='unavailable' if prior_missing or not len(n) else 'snapshot_only'
        completed=pd.to_numeric(info.get('Completed games in feed'),errors='coerce')
        parsed=pd.to_numeric(info.get('Game box scores parsed'),errors='coerce')
        game_coverage=bool(pd.notna(completed) and completed>0 and pd.notna(parsed) and parsed==completed)
        if len(s) and game_coverage and len(n) and len(p): coverage='archived_games_complete_unverified'
        elif len(s) and len(n) and len(p): coverage='partial_or_unverified_boxscores'
        row={'division':division,'team_id':tid,'team':name,'current_roster_players':len(current),
             'prior_roster_players':len(previous),'prior_stats_players':len(prior_stats),
             'matched_returning_players':len(returning),
             'unmatched_current_players_NOT_CONFIRMED_TRANSFERS':len(known_new),
             'prior_players_not_on_current_snapshot':len(previous-current),
             'evidence_quality':coverage,'completed_games_in_feed':int(completed) if pd.notna(completed) else None,
             'parsed_games':int(parsed) if pd.notna(parsed) else None,
             'returning_minutes_pct_documented':None,'returning_points_pct_documented':None,
             'returning_rebounds_pct_documented':None,'returning_assists_pct_documented':None,
             'caveats':[]}
        if prior_missing: row['caveats'].append('missing prior roster: no confirmed player continuity')
        if not len(n): row['caveats'].append('missing current roster')
        if not game_coverage: row['caveats'].append('historical box-score coverage incomplete or unverified')
        if not len(s): row['caveats'].append('no historical player totals')
        for key,label in [(minutes_key,'minutes'),(points_key,'points'),(rebound_key,'rebounds'),(assist_key,'assists')]:
            if key is None or not len(s): continue
            values=pd.to_numeric(s[key],errors='coerce')
            valid=values.notna() & (values>=0)
            denom=float(values[valid].sum())
            if denom>0 and len(n) and len(p):
                mask=s['Player ID'].astype(str).isin(returning) & valid
                row[f'returning_{label}_pct_documented']=round(100*float(values[mask].sum())/denom,2)
        if tid=='2697': row['caveats'].append('West Florida transition: 2025-26 D2 history not in ESPN D1 archive; never treat missing history as zero')
        if division.startswith('womens') and tid=='2426': row['caveats'].append('Navy: ESPN game 401823071 player box score missing in V102.1; shares provisional')
        output.append(row)
        for pid in sorted(current | previous):
            label='returning_id_match' if pid in returning else 'not_on_current_snapshot' if pid in previous else 'new_to_snapshot_unverified_origin'
            details.append({'division':division,'team_id':tid,'team':name,'player_id':pid,'status':label,
                            'current_roster':pid in current,'previous_roster':pid in previous,
                            'previous_stat_record':pid in prior_stats,
                            'warning':'Snapshot change does not establish transfer, recruitment, or departure'})
    return output,details

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data',default='data');ap.add_argument('--out',default='data/returning_production_v103')
    args=ap.parse_args(); root=Path(args.data); out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    summary={'version':103,'generated_at_utc':datetime.now(timezone.utc).isoformat(),'season':'2026-27',
             'notice':'Research only. Snapshot-matched IDs are not verified returning production; no origin inference or rating changes.',
             'divisions':{}}
    for sport in SPORTS:
        rows,details=records(root,sport)
        pd.DataFrame(rows).to_csv(out/f'{sport}_team_continuity.csv',index=False)
        pd.DataFrame(details).to_csv(out/f'{sport}_player_evidence.csv',index=False)
        summary['divisions'][sport]={'archive_team_ids':len(rows),'with_current_roster':sum(x['current_roster_players']>0 for x in rows),
            'with_prior_roster':sum(x['prior_roster_players']>0 for x in rows),
            'with_prior_player_stats':sum(x['prior_stats_players']>0 for x in rows),
            'with_complete_reported_boxscore_coverage':sum(x['evidence_quality']=='archived_games_complete_unverified' for x in rows),
            'returning_minutes_share_available':sum(x['returning_minutes_pct_documented'] is not None for x in rows),
            'known_exceptions':[x for x in rows if x['team_id']=='2697' or (sport.startswith('womens') and x['team_id']=='2426')]}
        print(sport, summary['divisions'][sport]['with_current_roster'],'teams with current roster; production shares',summary['divisions'][sport]['returning_minutes_share_available'],flush=True)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

if __name__=='__main__': main()

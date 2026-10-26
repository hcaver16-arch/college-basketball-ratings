"""Courtside V104: research-only player-origin and documented transfer production.
Reads saved V103-compatible archives; never touches forecasts or ratings.
"""
import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

DIVISIONS = ('mens-college-basketball','womens-college-basketball')
METRICS = {'minutes':('Minutes','Total Minutes','Minutes Played'),
           'points':('Points','PTS'), 'rebounds':('Rebounds','REB'),
           'assists':('Assists','AST')}

def read_archive(root, division, kind):
    path = root / f'{division}_{kind}.csv.gz'
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, dtype={'Team ID':'string', 'Player ID':'string'}, low_memory=False)
    if not {'Team ID','Player ID'}.issubset(frame.columns):
        raise ValueError(f'{path}: expected Team ID and Player ID')
    for key in ('Team ID','Player ID'):
        frame[key] = frame[key].astype('string').str.strip()
    frame = frame.dropna(subset=['Team ID','Player ID'])
    frame = frame[(frame['Team ID']!='') & (frame['Player ID']!='')]
    return frame.drop_duplicates(['Team ID','Player ID'],keep='last')

def find_column(frame, options):
    normalized = {str(c).lower().replace(' ','').replace('_',''):c for c in frame.columns}
    for name in options:
        candidate = normalized.get(name.lower().replace(' ','').replace('_',''))
        if candidate is not None:
            return candidate
    return None

def name_for(row, fallback):
    for key in ('Player','Player Name','Name','Athlete'):
        if key in row and pd.notna(row[key]) and str(row[key]).strip():
            return str(row[key])
    return fallback

def summarize(root, division):
    current = read_archive(root, division, 'current_rosters')
    previous = read_archive(root, division, 'previous_rosters')
    stats = read_archive(root, division, 'previous_stats')
    statuses = read_archive_status(root, division)
    if current.empty:
        return [], [], {'status':'no_current_rosters','teams':0}
    historical_teams = defaultdict(set)
    previous_same = defaultdict(set)
    current_by_team = defaultdict(set)
    historical_names = {}
    current_names = {}
    status_by_team = {}
    for _, row in previous.iterrows():
        tid,pid = str(row['Team ID']),str(row['Player ID'])
        historical_teams[pid].add(tid)
        previous_same[tid].add(pid)
        if pd.notna(row.get('Team')): historical_names[tid] = str(row['Team'])
    for _,row in current.iterrows():
        tid,pid=str(row['Team ID']),str(row['Player ID'])
        current_by_team[tid].add(pid)
        if pd.notna(row.get('Team')): current_names[tid]=str(row['Team'])
    if not statuses.empty:
        for _,row in statuses.iterrows(): status_by_team[str(row['Team ID'])]=row
    stat_cols={metric:find_column(stats, names) for metric,names in METRICS.items()}
    stats_index={(str(r['Team ID']),str(r['Player ID'])):r for _,r in stats.iterrows()}
    evidence=[]
    team_summaries=[]
    for tid in sorted(current_by_team):
        team_name=current_names.get(tid,historical_names.get(tid,tid))
        player_rows=current[current['Team ID'].eq(tid)]
        counts={'returning_same_id':0,'cross_school_unique_id':0,'cross_school_ambiguous_id':0,'unknown_origin':0}
        for _, player in player_rows.iterrows():
            pid=str(player['Player ID'])
            prior_teams=historical_teams.get(pid,set())
            other=sorted(prior_teams-{tid})
            if tid in prior_teams:
                classification='returning_same_id'
            elif len(other)==1:
                classification='cross_school_unique_id'
            elif len(other)>1:
                classification='cross_school_ambiguous_id'
            else:
                classification='unknown_origin'
            counts[classification]+=1
            origin=other[0] if classification=='cross_school_unique_id' else None
            prior_stat=stats_index.get((origin,pid)) if origin else None
            record={'division':division,'destination_team_id':tid,'destination_team':team_name,
                    'player_id':pid,'player_name':name_for(player,pid),'classification':classification,
                    'prior_team_id':origin,'prior_team':historical_names.get(origin,origin) if origin else None,
                    'candidate_prior_team_ids':';'.join(other) if other else None,
                    'previous_stat_record_at_origin':bool(prior_stat is not None),
                    'note':'Cross-school roster ID match, not independently verified enrollment or transfer eligibility' if origin else
                           'Prior-year roster ID present for same team; not independently verified continuity' if classification=='returning_same_id' else
                           'No unique cross-school origin; do not infer freshman or transfer'}
            for metric,col in stat_cols.items():
                value = pd.to_numeric(prior_stat.get(col),errors='coerce') if prior_stat is not None and col else float('nan')
                record[f'prior_{metric}_documented']=round(float(value),2) if pd.notna(value) and value>=0 else None
            evidence.append(record)
        matching=[r for r in evidence if r['destination_team_id']==tid and r['division']==division and r['classification']=='cross_school_unique_id']
        coverage=sum(bool(r['previous_stat_record_at_origin']) for r in matching)
        existing_status=status_by_team.get(tid)
        parsed=pd.to_numeric(existing_status.get('Game box scores parsed'),errors='coerce') if existing_status is not None else float('nan')
        completed=pd.to_numeric(existing_status.get('Completed games in feed'),errors='coerce') if existing_status is not None else float('nan')
        caveats=[]
        if not previous_same.get(tid): caveats.append('prior-season team roster unavailable; continuity cannot be assessed')
        if tid=='2697': caveats.append('West Florida: 2025-26 Division II historical coverage missing from D1 archive')
        if tid=='2426' and division.startswith('womens'): caveats.append('Navy: one previous-season player box score missing (401823071)')
        if pd.notna(parsed) and pd.notna(completed) and parsed < completed: caveats.append('own team historical box-score coverage incomplete')
        if counts['unknown_origin']: caveats.append('unknown origin includes freshmen, transfers from schools outside archive, and missing/changed IDs')
        summary={'division':division,'team_id':tid,'team':team_name,'current_players':len(current_by_team[tid]),
                 'prior_same_team_roster_players':len(previous_same.get(tid,set())),
                 **counts,'cross_school_with_documented_prior_stats':coverage,
                 'cross_school_missing_prior_stats':len(matching)-coverage,
                 'incoming_prior_minutes_documented':sum(r['prior_minutes_documented'] or 0 for r in matching),
                 'incoming_prior_points_documented':sum(r['prior_points_documented'] or 0 for r in matching),
                 'incoming_prior_rebounds_documented':sum(r['prior_rebounds_documented'] or 0 for r in matching),
                 'incoming_prior_assists_documented':sum(r['prior_assists_documented'] or 0 for r in matching),
                 'historical_boxscores_complete':bool(pd.notna(completed) and completed>0 and parsed==completed),
                 'caveats':'; '.join(caveats)}
        team_summaries.append(summary)
    status={'status':'research_only','teams':len(team_summaries),'current_players':len(evidence),
            'same_team_id_matches':sum(t['returning_same_id'] for t in team_summaries),
            'unique_cross_school_id_matches':sum(t['cross_school_unique_id'] for t in team_summaries),
            'ambiguous_cross_school_id_matches':sum(t['cross_school_ambiguous_id'] for t in team_summaries),
            'unknown_origin':sum(t['unknown_origin'] for t in team_summaries),
            'cross_school_with_origin_statistics':sum(t['cross_school_with_documented_prior_stats'] for t in team_summaries),
            'cautions':['Prior season roster and statistics are from ESPN archive and may be incomplete.',
                        'Cross-school ID match is evidence of a roster change, not verified transfer enrollment.',
                        'Incoming production totals cover documented matched players only; not team-level projections.',
                        'Prior stats are sourced from origin school, never from destination school.',
                        'Player identities are matched on exact ESPN IDs only; unmatched players are not labeled recruits.']}
    return team_summaries,evidence,status

def read_archive_status(root,division):
    path=root/f'{division}_collection_status.csv.gz'
    if not path.exists(): return pd.DataFrame()
    df=pd.read_csv(path,dtype={'Team ID':'string'},low_memory=False)
    if 'Team ID' in df:
        df['Team ID']=df['Team ID'].astype('string').str.strip()
        df=df.drop_duplicates('Team ID',keep='last')
    return df

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',default='data')
    parser.add_argument('--out',default='data/transfer_origin_v104')
    args=parser.parse_args()
    root,out=Path(args.data),Path(args.out)
    out.mkdir(parents=True,exist_ok=True)
    report={'version':104,'generated_at_utc':datetime.now(timezone.utc).isoformat(),
            'season':'2026-27','prior_season':'2025-26',
            'status':'RESEARCH_ONLY_EXACT_ID_ROSTER_MATCHES','divisions':{}}
    for division in DIVISIONS:
        teams,players,status=summarize(root,division)
        pd.DataFrame(teams).to_csv(out/f'{division}_origin_summary.csv',index=False)
        pd.DataFrame(players).to_csv(out/f'{division}_player_origins.csv',index=False)
        report['divisions'][division]=status
        print(division, 'teams',status['teams'],'cross-school matches',status.get('unique_cross_school_id_matches',0))
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__': main()

"""Read-only, conservative utilities for persisted basketball roster archives."""
from pathlib import Path
import pandas as pd
from transfer_tracking import identify_incoming
from league_transfer_lookup import match_candidates
from returning_production import calculate_returning_production

ROOT = Path(__file__).resolve().parent / 'data'
KINDS = ('previous_rosters','current_rosters','previous_stats','collection_status')

def _read(kind, sport):
    path=ROOT / f'{sport}_{kind}.csv.gz'
    if not path.is_file(): return pd.DataFrame()
    try:
        df=pd.read_csv(path,dtype={'Team ID':'string','Player ID':'string'},compression='gzip')
        if 'Roster season' in df:
            df['Roster season']=pd.to_numeric(df['Roster season'],errors='coerce')
        return df
    except (OSError,ValueError,EOFError,KeyError): return pd.DataFrame()

def load_saved_data(sport):
    return tuple(_read(k,sport) for k in KINDS)

def _ids(df):
    return set(df['Team ID'].dropna().astype(str)) if not df.empty and 'Team ID' in df else set()

def archive_counts(previous,current,stats,status,directory_size=None):
    previous_ids=_ids(previous); current_ids=_ids(current); stat_ids=_ids(stats)
    recorded=_ids(status)
    if not status.empty and {'Team ID','state'}.issubset(status.columns):
        completed=set(status.loc[status['state'].eq('collected'),'Team ID'].dropna().astype(str))
        retry=set(status.loc[status['state'].eq('retry'),'Team ID'].dropna().astype(str))
    else: completed=set();retry=set()
    both=previous_ids & current_ids
    return {'Directory schools':directory_size,'Attempted':len(recorded),
            'Collector succeeded':len(completed),'Needs retry':len(retry),
            'Previous rosters saved':len(previous_ids),'Current rosters saved':len(current_ids),
            'Both rosters saved':len(both),'Player totals saved':len(stat_ids),
            'Rosters and stats saved':len(both & stat_ids)}

def roster_archive_summary(old,new,stats,status):
    c=archive_counts(old,new,stats,status)
    return (f"Saved archive: {c['Both rosters saved']} schools with both roster snapshots; "
            f"{c['Rosters and stats saved']} also with prior-season player totals; "
            f"{c['Needs retry']} listed for retry. Saved does not mean independently verified complete.")

def team_saved_analysis(team_id,previous,current,stats):
    tid=str(team_id)
    if not _ids(previous).__contains__(tid) or not _ids(current).__contains__(tid):
        return None
    a=previous[previous['Team ID'].astype(str)==tid]
    b=current[current['Team ID'].astype(str)==tid]
    s=stats[stats['Team ID'].astype(str)==tid] if not stats.empty and 'Team ID' in stats else pd.DataFrame()
    summary=pd.DataFrame();audit=pd.DataFrame();warnings=[]
    if not s.empty:
        summary,audit,warnings=calculate_returning_production(pd.concat([a,b],ignore_index=True),s)
    return {'previous':a,'current':b,'stats':s,'returning':summary,'player_audit':audit,'warnings':warnings}

def build_team_roster_view(team_id,previous,current,stats):
    tid=str(team_id)
    if previous.empty or current.empty:return pd.DataFrame()
    a=previous[previous['Team ID'].astype(str)==tid]
    b=current[current['Team ID'].astype(str)==tid]
    if a.empty or b.empty:return pd.DataFrame()
    candidates,_=identify_incoming(pd.concat([a,b],ignore_index=True))
    if candidates.empty:return candidates
    return match_candidates(candidates,previous,stats)

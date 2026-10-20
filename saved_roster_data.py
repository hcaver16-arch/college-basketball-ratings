"""Read-only persisted archive for Streamlit. Never infer missing player totals or transfers."""
from pathlib import Path
import pandas as pd
from transfer_tracking import identify_incoming
from league_transfer_lookup import match_candidates
ROOT = Path(__file__).resolve().parent / "data"

def _read(kind,sport):
    path=ROOT / (sport + "_" + kind + ".csv.gz")
    if not path.exists(): return pd.DataFrame()
    try:
        frame=pd.read_csv(path,dtype={"Team ID":str,"Player ID":str},compression="gzip")
        if "Roster season" in frame.columns: frame["Roster season"]=pd.to_numeric(frame["Roster season"],errors="coerce")
        return frame
    except (OSError,ValueError,EOFError): return pd.DataFrame()

def load_saved_data(sport):
    old=_read("previous_rosters",sport)
    new=_read("current_rosters",sport)
    stats=_read("previous_stats",sport)
    status=_read("collection_status",sport)
    return old,new,stats,status

def roster_archive_summary(old,new,stats,status):
    count=lambda x: x["Team ID"].nunique() if not x.empty and "Team ID" in x else 0
    return (f"Persistent archive: {count(old)} schools with 2025–26 rosters, "
            f"{count(new)} with 2026–27 rosters, and {count(stats)} with prior-season player totals. "
            "These are coverage counts, not verified season completeness. "
            "Schools will appear as nightly batches finish.")

def build_team_roster_view(team_id,previous,current,stats):
    tid=str(team_id)
    a=previous[previous["Team ID"].astype(str)==tid]
    b=current[current["Team ID"].astype(str)==tid]
    if a.empty or b.empty: return pd.DataFrame()
    # identify_incoming does not classify when the two snapshots are identical.
    candidates,_=identify_incoming(pd.concat([a,b],ignore_index=True))
    if candidates.empty:return candidates
    return match_candidates(candidates,previous,stats)

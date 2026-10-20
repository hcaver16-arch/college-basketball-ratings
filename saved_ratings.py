"""Read persisted daily rating snapshots committed by GitHub Actions."""
from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).resolve().parent/'data'/'ratings'

def load_ratings(sport):
    root=ROOT/sport
    file=root/'latest.csv.gz'
    status=root/'status.json'
    if not (file.exists() and status.exists()):return None,None
    try:
        df=pd.read_csv(file,compression='gzip',dtype={'Team ID':str})
        meta=json.loads(status.read_text())
        if df.empty or not {'Team ID','Team','Current power','Rank'}.issubset(df.columns):return None,None
        return df,meta
    except (OSError,ValueError,KeyError,json.JSONDecodeError):return None,None

def load_history(sport,team_id=None):
    file=ROOT/sport/'history.csv.gz'
    if not file.exists():return pd.DataFrame()
    try:
        df=pd.read_csv(file,compression='gzip',dtype={'Team ID':str})
        if team_id is not None:df=df[df['Team ID']==str(team_id)]
        return df.sort_values('Snapshot date')
    except (OSError,ValueError,KeyError):return pd.DataFrame()

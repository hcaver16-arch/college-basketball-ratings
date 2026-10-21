"""NCAA NET-driven quadrants; no modeled/previous-season ranking substitutions."""
from __future__ import annotations
from datetime import date
from pathlib import Path
import pandas as pd

CUTS = {
    "Men's": {"Home": (30,75,160), "Neutral": (50,100,200), "Away": (75,135,240)},
    "Women's": {"Home": (25,55,90), "Neutral": (35,65,105), "Away": (45,80,130)},
}
SEASON = "2026-27"

def quadrant(opponent_rank, location, division):
    try:
        rank = int(opponent_rank)
    except (ValueError, TypeError):
        return "NET unavailable"
    if rank < 1 or location not in CUTS.get(division, {}):
        return "NET unavailable"
    a,b,c = CUTS[division][location]
    return "Q1" if rank<=a else "Q2" if rank<=b else "Q3" if rank<=c else "Q4"

def load_net(division, root="data/net"):
    """Only accept dated, current-season official NCAA NET snapshots, by ESPN team id.

    CSV columns: team_id, net_rank, snapshot_date, season, source
    Rank data must be sourced and verified before it is committed here.
    """
    slug = 'mens' if division == "Men's" else 'womens'
    path = Path(root) / f"{slug}_net.csv"
    if not path.exists():
        return {}, "No official 2026–27 NCAA NET snapshot has been loaded."
    try:
        df = pd.read_csv(path, dtype=str)
        required = {'team_id','net_rank','snapshot_date','season','source'}
        if not required.issubset(df.columns):
            return {}, f"NET file missing columns: {', '.join(sorted(required - set(df.columns)))}"
        df = df[df['season'].str.strip() == SEASON].copy()
        df['parsed_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce', utc=True)
        df['rank'] = pd.to_numeric(df['net_rank'], errors='coerce')
        df = df[df['parsed_date'].notna() & df['rank'].notna() & (df['rank'] >= 1)].copy()
        df = df[df['parsed_date'].dt.date <= date.today()]
        df = df[df['source'].fillna('').str.contains('ncaa',case=False,regex=False)]
        if df.empty:
            return {}, "No valid dated 2026–27 NCAA NET rankings are available."
        latest = df['parsed_date'].max()
        df = df[df['parsed_date'] == latest].drop_duplicates('team_id')
        return dict(zip(df['team_id'].str.strip(), df['rank'].astype(int))), f"Official NCAA NET snapshot: {latest.date().isoformat()} ({len(df)} teams)"
    except Exception as exc:
        return {}, f"Cannot load NET rankings: {type(exc).__name__}: {exc}"

def annotate_games(frame, ranks, d1_ids, division):
    result = frame.copy()
    def labels(r):
        home,away=str(r['Home ID']),str(r['Away ID'])
        if home not in d1_ids or away not in d1_ids:
            return pd.Series({'Home quadrant':'Non-D1','Away quadrant':'Non-D1','Home opponent NET':None,'Away opponent NET':None})
        hr, ar = ranks.get(home), ranks.get(away)
        home_loc = 'Neutral' if r['Venue']=='Neutral' else 'Home'
        away_loc = 'Neutral' if r['Venue']=='Neutral' else 'Away'
        return pd.Series({'Home quadrant':quadrant(ar,home_loc,division), 'Away quadrant':quadrant(hr,away_loc,division), 'Home opponent NET':ar, 'Away opponent NET':hr})
    if result.empty:
        for key in ('Home quadrant','Away quadrant','Home opponent NET','Away opponent NET'):
            result[key]=pd.Series(dtype=object)
        return result
    return pd.concat([result, result.apply(labels,axis=1)],axis=1)

def quadrant_records(frame, team_id):
    """W-L records against D1 only; quadrants reflect current NET snapshot."""
    tally = {f'Q{i}':[0,0] for i in range(1,5)}
    for _,g in frame.iterrows():
        if g.get('Status')!='Final': continue
        home=str(g.get('Home ID'))==str(team_id)
        away=str(g.get('Away ID'))==str(team_id)
        if not (home or away): continue
        quad=g.get('Home quadrant') if home else g.get('Away quadrant')
        if quad not in tally: continue
        ours=pd.to_numeric(g.get('Home score') if home else g.get('Away score'),errors='coerce')
        theirs=pd.to_numeric(g.get('Away score') if home else g.get('Home score'),errors='coerce')
        if pd.isna(ours) or pd.isna(theirs) or ours==theirs: continue
        tally[quad][0 if ours>theirs else 1]+=1
    return tally

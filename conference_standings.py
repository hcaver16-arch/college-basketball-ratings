"""Conference results from loaded completed games; tentative seed preview, not official seeding."""
import math
import pandas as pd


def standings_for_conference(members: pd.DataFrame, games: pd.DataFrame):
    required = {'Team ID', 'Team'}
    if not required.issubset(members.columns):
        return pd.DataFrame()
    teams = members.drop_duplicates('Team ID').copy()
    teams['Team ID'] = teams['Team ID'].astype(str)
    id_to_name = dict(zip(teams['Team ID'], teams['Team']))
    records = {tid: {'Team ID':tid, 'Team':name, 'Conference W':0,'Conference L':0,'Overall W':0,'Overall L':0} for tid,name in id_to_name.items()}
    needed = {'Home ID','Away ID','Status','Home score','Away score'}
    if not isinstance(games,pd.DataFrame) or not needed.issubset(games.columns):
        return pd.DataFrame(records.values())
    game_rows = games.drop_duplicates('Game ID') if 'Game ID' in games.columns else games
    for _, g in game_rows.iterrows():
        if str(g['Status']) != 'Final':
            continue
        h, a = str(g['Home ID']), str(g['Away ID'])
        hs, aws = pd.to_numeric(g['Home score'],errors='coerce'),pd.to_numeric(g['Away score'],errors='coerce')
        if pd.isna(hs) or pd.isna(aws) or hs == aws:
            continue
        winner, loser = (h,a) if hs > aws else (a,h)
        if winner in records: records[winner]['Overall W'] += 1
        if loser in records: records[loser]['Overall L'] += 1
        if h in records and a in records:
            records[winner]['Conference W'] += 1
            records[loser]['Conference L'] += 1
    result = pd.DataFrame(records.values())
    if result.empty: return result
    played = result['Conference W'] + result['Conference L']
    result['Conference PCT'] = (result['Conference W']/played.where(played.ne(0))).fillna(0)
    result['Power'] = result['Team ID'].map(teams.set_index('Team ID')['Current power'].to_dict()) if 'Current power' in teams.columns else 0
    result['Power'] = pd.to_numeric(result['Power'],errors='coerce')
    # Ties are not official: deterministic display uses rating, not league tiebreak rules.
    return result.sort_values(['Conference PCT','Conference W','Power','Team'],ascending=[False,False,False,True],kind='stable').reset_index(drop=True)


def provisional_bracket(seeds: pd.DataFrame):
    """Generic illustrative single elimination slotting with high-seed byes, NOT an official conference format."""
    if seeds.empty: return []
    n = len(seeds)
    size = 1 << (n-1).bit_length()
    # adjacent pair seed positions based on conventional high-low first-round pairing
    slots=[]
    for upper_seed in range(1, size//2+1):
        lower_seed = size + 1 - upper_seed
        upper = seeds.iloc[upper_seed-1]['Team'] if upper_seed<=n else 'BYE'
        lower = seeds.iloc[lower_seed-1]['Team'] if lower_seed<=n else 'BYE'
        slots.append((upper_seed,upper,lower_seed,lower))
    return slots

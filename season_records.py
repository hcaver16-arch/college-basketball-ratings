"""Season win/loss records computed from final scores, independent of view dates."""
from __future__ import annotations
import pandas as pd


def records_before_game(schedule: pd.DataFrame, game_date, game_id=None) -> dict[str, tuple[int, int]]:
    """Pregame W-L counts through the previous calendar day.

    No future outcomes or the current game are included. Caller must provide
    the full available season schedule, not a filtered Games page.
    """
    if not isinstance(schedule, pd.DataFrame) or schedule.empty:
        return {}
    needed = {'Date', 'Status', 'Home ID', 'Away ID', 'Home score', 'Away score'}
    if not needed.issubset(schedule.columns):
        return {}
    target = pd.to_datetime(game_date, errors='coerce')
    if pd.isna(target):
        return {}
    target = target.date()
    frame = schedule.copy()
    frame['_day'] = pd.to_datetime(frame['Date'], errors='coerce').dt.date
    frame = frame[(frame['_day'] < target) & (frame['Status'] == 'Final')]
    if game_id is not None and 'Game ID' in frame.columns:
        frame = frame[frame['Game ID'].astype(str) != str(game_id)]
    frame = frame.drop_duplicates('Game ID') if 'Game ID' in frame.columns else frame
    frame['_home_score'] = pd.to_numeric(frame['Home score'], errors='coerce')
    frame['_away_score'] = pd.to_numeric(frame['Away score'], errors='coerce')
    frame = frame.dropna(subset=['_home_score', '_away_score'])
    totals: dict[str, list[int]] = {}
    for _, row in frame.iterrows():
        home, away = str(row['Home ID']), str(row['Away ID'])
        if not home or not away or home == 'nan' or away == 'nan':
            continue
        hs, aws = float(row['_home_score']), float(row['_away_score'])
        if hs == aws:
            continue
        for team in (home, away):
            totals.setdefault(team, [0, 0])
        totals[home][0 if hs > aws else 1] += 1
        totals[away][0 if aws > hs else 1] += 1
    return {k: tuple(v) for k, v in totals.items()}


def game_records(schedule: pd.DataFrame, game) -> tuple[str, str]:
    counts = records_before_game(schedule, game.get('Date'), game.get('Game ID'))
    away = counts.get(str(game.get('Away ID')), (0, 0))
    home = counts.get(str(game.get('Home ID')), (0, 0))
    # Completed games display records including the final result.
    # records_before_game excludes this fixture, so it is counted exactly once.
    if str(game.get('Status')) == 'Final':
        try:
            away_score = float(game.get('Away score'))
            home_score = float(game.get('Home score'))
            if pd.notna(away_score) and pd.notna(home_score) and away_score != home_score:
                away = (away[0] + int(away_score > home_score), away[1] + int(away_score < home_score))
                home = (home[0] + int(home_score > away_score), home[1] + int(home_score < away_score))
        except (TypeError, ValueError):
            pass
    return f'{away[0]}–{away[1]}', f'{home[0]}–{home[1]}'

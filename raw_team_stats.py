"""Completed-game team stats for Courtside, including *raw* efficiency.

Display-only. Uses unofficial ESPN summary API; failures never create numbers.
No opponent adjustments, no changes to power ratings or predictions.
"""
from __future__ import annotations
import math
import re
import pandas as pd
import requests
import streamlit as st

STAT_NAMES = {
    'fieldGoalsMade-fieldGoalsAttempted':'fg',
    'threePointFieldGoalsMade-threePointFieldGoalsAttempted':'three',
    'freeThrowsMade-freeThrowsAttempted':'ft',
    'offensiveRebounds':'oreb', 'defensiveRebounds':'dreb',
    'totalRebounds':'reb', 'assists':'ast', 'turnovers':'tov',
    'steals':'stl', 'blocks':'blk', 'points':'points',
}

def _number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None

def _pair(value):
    match = re.fullmatch(r'\s*(\d+)\s*[-/]\s*(\d+)\s*', str(value))
    return (int(match.group(1)), int(match.group(2))) if match else None

@st.cache_data(ttl=21600, show_spinner=False)
def _boxscore(game_id, league):
    """One event's two team totals, with final score from official ESPN game header."""
    if not re.fullmatch(r'\d{6,12}', str(game_id)):
        return {}
    sport = 'womens-college-basketball' if str(league).lower().startswith('women') else 'mens-college-basketball'
    try:
        response = requests.get(
            f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/summary',
            params={'event':str(game_id)}, timeout=10)
        response.raise_for_status()
        document = response.json()
        output = {}
        for item in document.get('boxscore', {}).get('teams', []):
            tid = str(item.get('team', {}).get('id', ''))
            if not tid:
                continue
            stats = {}
            for stat in item.get('statistics', []):
                name = str(stat.get('name') or stat.get('abbreviation') or '')
                value = stat.get('displayValue', stat.get('value'))
                key = STAT_NAMES.get(name)
                if key:
                    stats[key] = _pair(value) if key in ('fg', 'three', 'ft') else _number(value)
                elif name in ('fieldGoalsMade', 'fieldGoalsAttempted',
                              'threePointFieldGoalsMade', 'threePointFieldGoalsAttempted',
                              'freeThrowsMade', 'freeThrowsAttempted'):
                    stats[name] = _number(value)
            for key, stem in (('fg', 'fieldGoals'), ('three', 'threePointFieldGoals'), ('ft', 'freeThrows')):
                if key not in stats:
                    a, b = stats.get(stem+'Made'), stats.get(stem+'Attempted')
                    if a is not None and b is not None:
                        stats[key] = (a, b)
            output[tid] = stats
        # Read final scores from game header. ESPN team box-score rows often omit points.
        competitions = document.get('header', {}).get('competitions', [])
        if competitions:
            competition = competitions[0]
            state = competition.get('status', {}).get('type', {})
            if not state.get('completed', False) and str(state.get('name', '')).lower() not in ('status_final',):
                return {}
            for participant in competition.get('competitors', []):
                tid = str(participant.get('team', {}).get('id', ''))
                if tid in output:
                    score = _number(participant.get('score'))
                    if score is not None:
                        output[tid]['points'] = score
            # Regulation basketball is 40 minutes; OT games require length information
            # for tempo, and are omitted from the tempo estimate.
            output['_overtime'] = bool(_number(competition.get('status', {}).get('period')) and
                                   _number(competition.get('status', {}).get('period')) > (4 if sport.startswith('womens') else 2))
        else:
            # Without a verified final game header we should not calculate efficiency.
            return {}
        return output
    except (requests.RequestException, ValueError, TypeError, KeyError):
        return {}

def _possession_estimate(stat):
    fg, ft = stat.get('fg'), stat.get('ft')
    tov, oreb = stat.get('tov'), stat.get('oreb')
    if (not isinstance(fg, tuple) or not isinstance(ft, tuple)
            or tov is None or oreb is None):
        return None
    value = fg[1] + .44 * ft[1] + tov - oreb
    return value if value > 0 else None

def team_raw_stats(games, tid, league, *, before=None, max_games=45):
    """Return validated aggregates for completed games visible in full-season source.

    Efficiency uses only games with both teams' final points and possession inputs:
      possessions = average(FGA + .44*FTA - ORB + TOV) for two teams
      OffEff = 100 * points / possessions
      DefEff = 100 * opponent points / possessions.
    This common estimator is approximate; numbers are not opponent-adjusted.
    """
    if not isinstance(games, pd.DataFrame) or games.empty:
        return None
    needed = {'Game ID', 'Status', 'Home ID', 'Away ID'}
    if not needed.issubset(games.columns):
        return None
    selected = games[(games['Home ID'].astype(str) == str(tid)) |
                     (games['Away ID'].astype(str) == str(tid))].copy()
    selected = selected[selected['Status'].astype(str).str.contains('final', case=False, na=False)]
    if 'Date' in selected:
        selected['_date'] = pd.to_datetime(selected['Date'], errors='coerce', utc=True)
        if before is not None:
            cutoff = pd.to_datetime(before, errors='coerce', utc=True)
            if pd.notna(cutoff):
                selected = selected[selected['_date'] < cutoff]
        selected = selected.sort_values('_date')
    ids = selected['Game ID'].dropna().astype(str).drop_duplicates().tail(max_games).tolist()
    totals = {key:0. for key in ('fgm','fga','tpm','tpa','ftm','fta','reb','oreb','dreb','ast','tov','stl','blk')}
    counts = {key:0 for key in totals}
    found = 0
    score_games = 0
    scored_points = 0.0
    eff_games = 0
    points, opponent_points, possessions = 0., 0., 0.
    tempo_possessions, tempo_games = 0., 0
    for gid in ids:
        box = _boxscore(gid, league)
        stat = box.get(str(tid), {})
        if not stat:
            continue
        found += 1
        # ESPN completed-game header totals; only expose PPG for full sample coverage.
        scored = stat.get('points')
        if scored is not None:
            scored_points += float(scored)
            score_games += 1
        for key, made, attempted in (('fg','fgm','fga'), ('three','tpm','tpa'), ('ft','ftm','fta')):
            pair = stat.get(key)
            if pair is not None:
                totals[made] += pair[0]; totals[attempted] += pair[1]
                counts[made] += 1; counts[attempted] += 1
        for key in ('reb','oreb','dreb','ast','tov','stl','blk'):
            value = stat.get(key)
            if value is not None:
                totals[key] += value; counts[key] += 1
        matching = selected[selected['Game ID'].astype(str) == gid]
        if matching.empty:
            continue
        game = matching.iloc[0]
        oid = str(game['Away ID'] if str(game['Home ID']) == str(tid) else game['Home ID'])
        other = box.get(oid, {})
        own_pos = _possession_estimate(stat)
        other_pos = _possession_estimate(other)
        own_pts, other_pts = stat.get('points'), other.get('points')
        if (own_pos is None or other_pos is None or own_pts is None or other_pts is None):
            continue
        game_pos = (own_pos + other_pos) / 2
        possessions += game_pos
        points += own_pts
        opponent_points += other_pts
        eff_games += 1
        if not box.get('_overtime', False):
            tempo_possessions += game_pos
            tempo_games += 1
    if not found:
        return None
    result = {'validated':True, 'boxscore_games':found, 'eligible_final_games':len(ids),
              'efficiency_games':eff_games, 'tempo_games':tempo_games,
              'efficiency_method':'Two-team averaged box-score possession estimate; unadjusted'}
    def ratio(n, d, scale=1):
        if counts[n] != found or counts[d] != found or totals[d] <= 0:
            return None
        return scale * totals[n] / totals[d]
    if score_games == found:
        result['pts_pg'] = scored_points / found
    for target, key in (('reb_pg','reb'),('ast_pg','ast'),('tov_pg','tov'),('stl_pg','stl'),('blk_pg','blk')):
        if counts[key] == found:
            result[target] = totals[key] / found
    for name, n, d in (('fg_pct','fgm','fga'),('three_pct','tpm','tpa'),('ft_pct','ftm','fta')):
        value = ratio(n,d,100)
        if value is not None:result[name] = value
    if all(counts[key] == found for key in ('fgm','fga','tpm')) and totals['fga'] > 0:
        result['efg_pct'] = 100 * (totals['fgm'] + .5*totals['tpm']) / totals['fga']
    if all(counts[key] == found for key in ('fgm','fga','tpm','tpa')) and totals['fga'] > totals['tpa']:
        result['two_pct'] = 100 * (totals['fgm'] - totals['tpm']) / (totals['fga'] - totals['tpa'])
    if counts['ast'] == found and counts['tov'] == found and totals['tov'] > 0:
        result['ast_tov'] = totals['ast'] / totals['tov']
    if counts['ast'] == found and counts['fgm'] == found and totals['fgm'] > 0:
        result['ast_pct'] = 100 * totals['ast'] / totals['fgm']
    if counts['fta'] == found and counts['fga'] == found and totals['fga'] > 0:
        result['ftr'] = totals['fta'] / totals['fga']
    if eff_games > 0 and possessions > 0:
        result['off_eff'] = 100 * points / possessions
        result['def_eff'] = 100 * opponent_points / possessions
        result['net_eff'] = result['off_eff'] - result['def_eff']
        result['possessions'] = possessions / eff_games
    if tempo_games > 0:
        result['tempo'] = tempo_possessions / tempo_games
    return result

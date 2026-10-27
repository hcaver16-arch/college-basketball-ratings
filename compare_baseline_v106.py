"""Research-only comparison of frozen saved Courtside ratings and V105 roster signals.
Never modifies live snapshots, application code, or predictions.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

DIVISIONS = ('mens-college-basketball', 'womens-college-basketball')
REQUIRED_V105 = {'team_id', 'team', 'data_available', 'illustrative_adjustment_points', 'experimental_roster_index', 'roster_index_rank'}

def numbers(s):
    return pd.to_numeric(s, errors='coerce')

def load_baseline(path):
    if not path.is_file():
        return None, f'Baseline snapshot missing: {path}'
    frame = pd.read_csv(path, compression='infer', dtype={'Team ID':'string'}, low_memory=False)
    needed = {'Team ID', 'Team', 'Current power', 'Rank'}
    if not needed.issubset(frame.columns):
        return None, f'Unexpected ratings schema at {path}: missing {sorted(needed-set(frame.columns))}'
    df = frame[['Team ID', 'Team', 'Current power', 'Rank']].copy()
    df.columns = ['team_id', 'baseline_team', 'baseline_rating', 'saved_rank']
    df['team_id'] = df.team_id.astype('string').str.strip()
    df['baseline_rating'] = numbers(df.baseline_rating)
    df['saved_rank'] = numbers(df.saved_rank)
    df = df[df.team_id.notna() & df.baseline_rating.notna()].copy()
    if df.team_id.duplicated().any():
        raise ValueError(f'Duplicate team IDs in {path}; cannot safely join')
    if df.empty:
        return None, f'No numeric baseline ratings in {path}'
    return df, None

def compare(division, root, max_adjustment):
    src = root / 'roster_experiment_v105' / f'{division}_experimental_roster_sensitivity.csv'
    if not src.is_file():
        raise FileNotFoundError(f'Run V105 first: {src}')
    roster = pd.read_csv(src, dtype={'team_id':'string'}, low_memory=False)
    missing = REQUIRED_V105 - set(roster.columns)
    if missing:
        raise ValueError(f'V105 fields missing for {division}: {sorted(missing)}')
    roster = roster.drop(columns=['baseline_rating', 'experimental_rating', 'baseline_rank', 'experimental_rank', 'rank_change'], errors='ignore')
    roster['team_id'] = roster.team_id.astype('string').str.strip()
    if roster.team_id.isna().any() or roster.team_id.duplicated().any():
        raise ValueError(f'Invalid/duplicate V105 IDs for {division}')
    baseline_path = root / 'ratings' / division / 'latest.csv.gz'
    base, error = load_baseline(baseline_path)
    info = {'teams_in_v105': len(roster), 'baseline_path': str(baseline_path), 'baseline_available': base is not None,
            'baseline_warning': error, 'matched_teams': 0, 'baseline_only_teams': 0, 'v105_only_teams': 0,
            'adjusted_teams': 0, 'unavailable_roster_teams_unchanged': 0, 'ranked_comparison_teams': 0}
    if base is None:
        return None, info
    info['baseline_only_teams'] = int((~base.team_id.isin(roster.team_id)).sum())
    info['v105_only_teams'] = int((~roster.team_id.isin(base.team_id)).sum())
    result = base.merge(roster, on='team_id', how='left', validate='one_to_one', indicator=True)
    result['division'] = division
    result['join_status'] = result.pop('_merge').astype(str)
    result['adjustment'] = numbers(result['illustrative_adjustment_points'])
    available = result['data_available'].astype('string').str.lower().eq('true')
    usable = result.join_status.eq('both') & available & result.adjustment.notna()
    result['research_adjustment'] = result.adjustment.where(usable, 0.0).clip(-max_adjustment, max_adjustment)
    result['experimental_rating'] = result.baseline_rating + result.research_adjustment
    result['baseline_rank_comparable'] = result.baseline_rating.rank(method='min', ascending=False).astype('Int64')
    result['experimental_rank'] = result.experimental_rating.rank(method='min', ascending=False).astype('Int64')
    result['rank_change_positive_is_improvement'] = result.baseline_rank_comparable - result.experimental_rank
    result['missing_roster_evidence'] = ~usable
    result['research_warning'] = result.get('quality_warning', pd.Series(index=result.index, dtype='object')).fillna('').astype(str)
    result.loc[result.join_status.ne('both'), 'research_warning'] = 'No V105 record: unchanged; NOT zero roster quality'
    result.loc[result.join_status.eq('both') & ~available, 'research_warning'] = 'Unavailable V105 signal: unchanged; NOT zero roster quality'
    info['matched_teams'] = int(result.join_status.eq('both').sum())
    info['adjusted_teams'] = int(usable.sum())
    info['unavailable_roster_teams_unchanged'] = int((~usable).sum())
    info['ranked_comparison_teams'] = len(result)
    info['mean_absolute_adjustment'] = round(float(result.research_adjustment.abs().mean()), 5)
    info['largest_absolute_rank_change'] = int(result.rank_change_positive_is_improvement.abs().max())
    info['max_adjustment_cap'] = max_adjustment
    info['interpretation'] = 'Sensitivity study; baseline is current saved ratings snapshot, not necessarily a frozen preseason snapshot. Not a prediction accuracy test.'
    return result, info

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data-root', type=Path, default=Path('data'))
    p.add_argument('--max-abs-adjustment', type=float, default=2.0)
    args=p.parse_args()
    if not (0 < args.max_abs_adjustment <= 2.0):
        p.error('max-abs-adjustment must be greater than zero and <= 2')
    dest=args.data_root/'baseline_comparison_v106'
    dest.mkdir(parents=True,exist_ok=True)
    summary={'version':106,'generated_at_utc':datetime.now(timezone.utc).isoformat(),
             'status':'RESEARCH_ONLY_NO_LIVE_RATING_OR_FORECAST_CHANGES',
             'baseline_kind':'SAVED_LATEST_SNAPSHOT_NOT_VERIFIED_PRESEASON',
             'limitations':['V105 coefficients are illustrative and unvalidated','Latest saved ratings can change over time; this is a point-in-time snapshot, not a historical backtest','No results-based validation, conference normalization, or recruiting assessment','Unavailable or unmatched roster signals yield zero experimental change, NOT assumed zero player talent','Rank comparisons cover teams present in saved baseline; unmatched baseline records are retained and unchanged'],
             'divisions':{}}
    for division in DIVISIONS:
        df,info=compare(division,args.data_root,args.max_abs_adjustment)
        summary['divisions'][division]=info
        if df is not None:
            df.to_csv(dest/f'{division}_baseline_comparison.csv',index=False)
            top=df.reindex(df.rank_change_positive_is_improvement.abs().sort_values(ascending=False).index).head(12)
            info['largest_rank_movements']=[{'team':str(r['baseline_team']),'baseline_rank':int(r['baseline_rank_comparable']),
                'experimental_rank':int(r['experimental_rank']), 'rank_change':int(r['rank_change_positive_is_improvement']),
                'illustrative_adjustment':round(float(r['research_adjustment']),4)} for _,r in top.iterrows()]
    (dest/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    main()

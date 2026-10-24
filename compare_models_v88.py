"""Compare V85 efficiency predictions with immutable, timestamped Courtside forecasts.

Never substitute current ratings or postgame snapshots for historical forecasts.
No retrospective fitting of blend weights. Outputs comparison only on identical games.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd


def summarize(df, column):
    a=df['actual_margin'].to_numpy(dtype=float)
    p=df[column].to_numpy(dtype=float)
    mask=np.isfinite(a)&np.isfinite(p)
    if not mask.any():return {'games':0}
    a,p=a[mask],p[mask]
    return {'games':int(len(a)), 'margin_mae':round(float(np.mean(np.abs(a-p))),3),
        'winner_accuracy_excluding_ties':round(float(np.mean((p[a!=0]>0)==(a[a!=0]>0))),4) if (a!=0).any() else None}


def compare(efficiency, forecasts, division):
    e=pd.read_csv(efficiency,dtype={'game_id':'string','home_id':'string','away_id':'string'})
    f=pd.read_csv(forecasts,dtype={'Game ID':'string','Home ID':'string','Away ID':'string'})
    need_e={'game_id','date','home_id','away_id','home_points','away_points','efficiency_margin','forecast_cutoff_utc','training_max_date'}
    need_f={'Game ID','Game start UTC','First forecast UTC','Home ID','Away ID','Baseline home margin','Division'}
    if missing:=need_e-set(e):raise ValueError(f'Efficiency predictions missing: {sorted(missing)}')
    if missing:=need_f-set(f):raise ValueError(f'Courtside forecast archive missing: {sorted(missing)}')
    if e.game_id.duplicated().any() or f['Game ID'].duplicated().any():raise ValueError('Duplicate game IDs; refusing ambiguous forecasts')
    accepted={'mens':'mens-college-basketball','womens':'womens-college-basketball'}
    if division not in accepted:raise ValueError('Invalid division')
    f=f[f['Division']==accepted[division]].copy()
    e=e.copy()
    for c in ('date','forecast_cutoff_utc','training_max_date'):e[c]=pd.to_datetime(e[c],errors='coerce',utc=True)
    for c in ('Game start UTC','First forecast UTC'):f[c]=pd.to_datetime(f[c],errors='coerce',utc=True)
    for c in ('home_points','away_points','efficiency_margin'):e[c]=pd.to_numeric(e[c],errors='coerce')
    f['Baseline home margin']=pd.to_numeric(f['Baseline home margin'],errors='coerce')
    # IMPORTANT: V85 predictions are computed at seven-day frozen snapshot boundaries.
    # Training must end before snapshot cutoff AND before actual game's scheduled start.
    m=e.merge(f,left_on='game_id',right_on='Game ID',how='inner',validate='one_to_one')
    aligned=(m['home_id']==m['Home ID'])&(m['away_id']==m['Away ID'])
    pregame=(m['First forecast UTC']<m['Game start UTC']) & (m['forecast_cutoff_utc']<=m['date']) & (m['training_max_date']<m['forecast_cutoff_utc']) & (m['training_max_date']<m['Game start UTC'])
    # Dates are stored as UTC calendar dates in V85; validate game start calendar day matches.
    date_match=m['date'].dt.date==m['Game start UTC'].dt.date
    valid=aligned&pregame&date_match&m[['home_points','away_points','efficiency_margin','Baseline home margin']].notna().all(axis=1)
    out=m.loc[valid].copy()
    out['actual_margin']=out['home_points']-out['away_points']
    out['courtside_margin']=out['Baseline home margin']
    out['blend_50_50_margin']=(out['efficiency_margin']+out['courtside_margin'])/2
    cols=['game_id','date','home_id','away_id','actual_margin','efficiency_margin','courtside_margin','blend_50_50_margin','First forecast UTC','Game start UTC','forecast_cutoff_utc','training_max_date']
    out=out[cols].copy()
    summary={'division':division,'efficiency_game_count':int(len(e)),'archive_game_count_for_division':int(len(f)),
             'matching_game_ids':int(len(m)),'valid_same_game_comparisons':int(len(out)),
             'excluded_matches':int(len(m)-len(out)),
             'efficiency':summarize(out,'efficiency_margin'),
             'courtside_official_baseline':summarize(out,'courtside_margin'),
             'fixed_equal_blend_exploratory':summarize(out,'blend_50_50_margin'),
             'status':'COMPARISON_AVAILABLE' if len(out) else 'NO_VALID_HISTORICAL_FORECAST_OVERLAP',
             'warning':'Only identical games with authentic pre-tip archive forecasts. A 50/50 blend is illustrative, not out-of-sample-optimized. No betting validation.'}
    if len(out):
        out['month']=out['date'].dt.strftime('%Y-%m')
        summary['monthly']={month:{'games':len(g),'efficiency':summarize(g,'efficiency_margin'), 'courtside':summarize(g,'courtside_margin'),'fixed_blend':summarize(g,'blend_50_50_margin')} for month,g in out.groupby('month')}
    return out,summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--efficiency',required=True)
    parser.add_argument('--forecasts',required=True)
    parser.add_argument('--division',required=True,choices=['mens','womens'])
    parser.add_argument('--output-dir',required=True)
    args=parser.parse_args()
    out,report=compare(args.efficiency,args.forecasts,args.division)
    folder=Path(args.output_dir);folder.mkdir(parents=True,exist_ok=True)
    out.to_csv(folder/'same_game_comparison.csv',index=False)
    (folder/'comparison_summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(report,indent=2,allow_nan=False))

if __name__=='__main__':main()

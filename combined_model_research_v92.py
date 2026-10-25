"""Courtside V92: chronological, research-only conditional combination study.

Requires V91 candidate_game_predictions.csv.gz generated from pregame forecasts.
Training: games before evaluation date; evaluation: games on/after the date.
No production changes, no model selection on evaluation partition.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

REQUIRED = ['game_id','date','home_points','away_points','on_court_proxy_margin','cap_uncapped','efficiency_margin','forecast_cutoff_utc','neutral_site']


def validate(data):
    missing = [c for c in REQUIRED if c not in data]
    if missing: raise ValueError(f'Missing V91 columns: {missing}')
    x = data.copy()
    if x['game_id'].astype(str).duplicated().any(): raise ValueError('Duplicate game IDs')
    x['date'] = pd.to_datetime(x.date, utc=True, errors='coerce')
    x['cutoff'] = pd.to_datetime(x.forecast_cutoff_utc, utc=True, errors='coerce')
    if x.date.isna().any() or x.cutoff.isna().any() or (x.cutoff > x.date).any():
        raise ValueError('Missing/invalid forecast timestamps; possible future leakage')
    for c in ['home_points','away_points','on_court_proxy_margin','cap_uncapped','efficiency_margin']:
        x[c] = pd.to_numeric(x[c], errors='coerce')
    x = x.dropna(subset=['home_points','away_points','on_court_proxy_margin','cap_uncapped','efficiency_margin']).copy()
    if x.empty: raise ValueError('No usable matched predictions')
    x['actual'] = x.home_points - x.away_points
    x['month'] = x.date.dt.strftime('%Y-%m')
    return x.sort_values(['date','game_id']).reset_index(drop=True)


def evaluate(df, col):
    if df.empty: return {'games':0,'mae':None,'winner_accuracy':None,'bias_actual_minus_predicted':None}
    a = df.actual.to_numpy(float)
    p = df[col].to_numpy(float)
    valid = (a != 0) & (p != 0)
    return {'games':len(df), 'mae':round(float(np.mean(np.abs(a-p))),4),
            'winner_accuracy':round(float(np.mean((a[valid]>0)==(p[valid]>0))),4) if valid.any() else None,
            'bias_actual_minus_predicted':round(float(np.mean(a-p)),4)}


def run(df, split='2026-02-01'):
    x=validate(df)
    timestamp=pd.Timestamp(split, tz='UTC')
    train=x[x.date<timestamp].copy()
    test=x[x.date>=timestamp].copy()
    if len(train)<100 or len(test)<100:
        return x, {'status':'INSUFFICIENT_SPLIT', 'training_games':len(train),'evaluation_games':len(test),
                   'reason':'Need at least 100 usable games in each partition; no selection performed.'}
    # Diagnostics: systematic signed home-margin offset could reflect site/score orientation,
    # not just a valid intercept. Report it, do NOT silently apply a home-court intercept.
    eff_bias=float((train.actual-train.efficiency_margin).mean())
    base_bias=float((train.actual-train.cap_uncapped).mean())
    # A simple affine efficiency calibration (slope + intercept), learned ONLY on training games.
    # Clamp slope to a reasonable interval, and report it; this is a diagnostic candidate.
    q=train.efficiency_margin.to_numpy(float)
    actual=train.actual.to_numpy(float)
    variance=float(np.var(q))
    slope=float(np.cov(q,actual,bias=True)[0,1]/variance) if variance>1e-10 else 1.0
    slope=float(np.clip(slope,0.5,1.5))
    intercept=float(np.mean(actual)-slope*np.mean(q))
    x['eff_calibrated']=slope*x.efficiency_margin+intercept
    # Use power proxy sign to decide the spread bucket; fixed before viewing test results.
    magnitude=x.cap_uncapped.abs()
    cols=['on_court_proxy_margin','cap_uncapped','efficiency_margin','eff_calibrated']
    for weight in (0.1,0.25,0.5):
        for adjusted, tag in [('efficiency_margin','raw'),('eff_calibrated','cal')]:
            name=f'global_{tag}_{int(weight*100)}'
            x[name]=(1-weight)*x.cap_uncapped+weight*x[adjusted]
            cols.append(name)
    for boundary in (12,20):
        for weight in (0.25,0.5):
            for adjusted,tag in [('efficiency_margin','raw'),('eff_calibrated','cal')]:
                name=f'conditional_ge{boundary}_{tag}_{int(weight*100)}'
                x[name]=np.where(magnitude>=boundary,(1-weight)*x.cap_uncapped+weight*x[adjusted],x.cap_uncapped)
                cols.append(name)
    train=x[x.date<timestamp]
    test=x[x.date>=timestamp]
    results={'status':'CHRONOLOGICAL_EXPLORATORY_RESEARCH','train_before':split,
             'training_games':len(train),'evaluation_games':len(test),
             'notes':['2025-26 was used for prior V91 discovery; this internal holdout is NOT an independent season.',
                      'Power model is reconstructed on-court only: no 2024-25 preseason priors or blending.',
                      'Raw efficiency margin conversion may be miscalibrated. Diagnose before treating blend as evidence.',
                      'Do not select production weights using this report. No live model changes.'],
             'efficiency_calibration':{'training_raw_signed_bias':round(eff_bias,4),
                                       'training_uncapped_power_signed_bias':round(base_bias,4),
                                       'calibrated_slope':round(slope,5),'calibrated_intercept':round(intercept,5),
                                       'interpretation':'Exploratory linear score calibration trained only on pre-split games; not validated for production.'},
             'train':{},'test':{},'test_by_spread':{},'test_by_month':{}}
    for c in cols:
        results['train'][c]=evaluate(train,c)
        results['test'][c]=evaluate(test,c)
    categories=pd.cut(test.cap_uncapped.abs(),[0,3,7,12,20,np.inf],labels=['0-3','3-7','7-12','12-20','20+'],include_lowest=True)
    test=test.assign(bucket=categories)
    essentials=['cap_uncapped','efficiency_margin','eff_calibrated','global_raw_25','global_cal_25','conditional_ge12_raw_50','conditional_ge12_cal_50']
    for bucket,g in test.groupby('bucket',observed=True):
        results['test_by_spread'][str(bucket)]={c:evaluate(g,c) for c in essentials}
    for month,g in test.groupby('month'):
        results['test_by_month'][month]={c:evaluate(g,c) for c in essentials}
    results['test_delta_vs_uncapped']={c:round(results['test'][c]['mae']-results['test']['cap_uncapped']['mae'],4) for c in cols if results['test'][c]['mae'] is not None}
    return x,results


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--predictions',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--split',default='2026-02-01')
    a=p.parse_args()
    predictions=pd.read_csv(a.predictions,dtype={'game_id':str,'home_id':str,'away_id':str})
    outputs,report=run(predictions,a.split)
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    (out/'v92_summary.json').write_text(json.dumps(report,indent=2)+'\n')
    if report['status']=='CHRONOLOGICAL_EXPLORATORY_RESEARCH':
        outputs.to_csv(out/'v92_candidate_predictions.csv.gz',index=False,compression='gzip')
    print(json.dumps({'status':report['status'],'training_games':report['training_games'],'evaluation_games':report['evaluation_games'],
        'calibration':report.get('efficiency_calibration'), 'test':report.get('test'), 'test_delta_vs_uncapped':report.get('test_delta_vs_uncapped')},indent=2))

if __name__=='__main__': main()

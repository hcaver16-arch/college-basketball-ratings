"""Locked 2024-25 holdout comparison. No training or weight selection on holdout.
Requires paired forecasts from V91 and V85; study is proxy-only, not production model.
"""
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

# Frozen exploratory calibration coefficients from V92 2025-26 before-Feb-1 training.
COEFFS={'mens': (1.38631,-8.71148), 'womens': (1.5,-9.62317)}

def assess(x,pred):
    a=x['actual'].to_numpy(float); f=np.asarray(pred,dtype=float)
    v=(a!=0)&(f!=0)
    return {'games':len(a),'mae':round(float(np.abs(a-f).mean()),4),'winner_accuracy':round(float(((a[v]>0)==(f[v]>0)).mean()),4) if v.any() else None,
            'signed_bias':round(float((a-f).mean()),4)}

def compare(df, division):
    if division not in COEFFS:raise ValueError('Invalid division')
    required={'game_id','date','home_points','away_points','forecast_cutoff_utc','on_court_proxy_margin','cap_uncapped','efficiency_margin','neutral_site'}
    if not required.issubset(df):raise ValueError(f'Missing columns {required-set(df)}')
    d=df.copy(); d['date']=pd.to_datetime(d.date,utc=True,errors='coerce');d['cutoff']=pd.to_datetime(d.forecast_cutoff_utc,utc=True,errors='coerce')
    if d.game_id.astype(str).duplicated().any() or d.date.isna().any() or d.cutoff.isna().any() or (d.cutoff>d.date).any():raise ValueError('Duplicate IDs or invalid pregame cutoff')
    if (d.date.dt.year>2025).any() or (d.date.dt.year<2024).any() or not d.date.dt.strftime('%Y-%m').between('2024-11','2025-04').all():raise ValueError('Holdout MUST be 2024-25, not the discovery season')
    for c in ('home_points','away_points','on_court_proxy_margin','cap_uncapped','efficiency_margin'):
        d[c]=pd.to_numeric(d[c],errors='coerce')
    d=d.dropna(subset=['home_points','away_points','on_court_proxy_margin','cap_uncapped','efficiency_margin'])
    if len(d)<100:raise ValueError('Insufficient matched holdout games (<100)')
    d['actual']=d.home_points-d.away_points
    slope,intercept=COEFFS[division]
    e=slope*d.efficiency_margin+intercept
    power=d.cap_uncapped
    heavy=power.abs()>=12
    candidates={'capped_power':d.on_court_proxy_margin,'uncapped_power':power,'raw_efficiency':d.efficiency_margin,
                'calibrated_efficiency':e,
                'blend_10pct_cal':.90*power+.10*e,
                'blend_25pct_cal':.75*power+.25*e,
                'conditional_12plus_50pct_cal':np.where(heavy,.5*power+.5*e,power)}
    report={'status':'INDEPENDENT_SEASON_RESEARCH_PROXY','division':division,'season':'2024-25','games':len(d),
            'locked_from':'V92 2025-26 coefficients; no fitting or candidate selection on this season',
            'calibration':{'slope':slope,'intercept':intercept},
            'warning':'Still on-court proxy, not full official Courtside; historical preseason priors absent. Choose production settings only after additional checks.',
            'overall':{name:assess(d,pred) for name,pred in candidates.items()},'by_spread':{}}
    cuts=pd.cut(power.abs(),bins=[-0.01,3,7,12,20,np.inf],labels=['0-3','3-7','7-12','12-20','20+'])
    for label in cuts.dropna().unique():
        mask=(cuts==label).to_numpy()
        sub=d.loc[mask]
        report['by_spread'][str(label)]={name:assess(sub,np.asarray(pred)[mask]) for name,pred in candidates.items()}
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--predictions',required=True);ap.add_argument('--division',choices=['mens','womens'],required=True);ap.add_argument('--out',required=True)
    a=ap.parse_args(); d=pd.read_csv(a.predictions,dtype={'game_id':str,'home_id':str,'away_id':str}); report=compare(d,a.division)
    p=Path(a.out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'division':a.division,'status':report['status'],'games':report['games'],'overall':report['overall']},indent=2))
if __name__=='__main__': main()

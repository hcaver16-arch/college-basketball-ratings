"""V94 research-only, venue-aware margin postprocessor. No changes to rating fit or production.

Training: 2025-26 dates strictly BEFORE Feb 1. Freeze venue coefficients and
preselected blend weights. Evaluation: later 2025-26 and 2024-25, separately.
Subtract V85's empirical home-only margin first; explicitly estimate distinct
neutral-site intercept and the incremental home-site effect from training games.
Neither represents a new possession-level fitted home-effect coefficient.
"""
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

SPLIT=pd.Timestamp('2026-02-01',tz='UTC')
MODELS=('capped_power','uncapped_power','v85_efficiency','venue_corrected_efficiency','blend10','blend25','conditional12_50')

def prepare(candidates, efficiency):
    a=candidates.copy(); b=efficiency.copy()
    for z in (a,b):
        if 'game_id' not in z: raise ValueError('Missing game_id')
        z['game_id']=z.game_id.astype(str).str.strip()
        if z.game_id.duplicated().any():raise ValueError('Duplicate game IDs')
    mandatory={'date','home_points','away_points','neutral_site','forecast_cutoff_utc','on_court_proxy_margin','cap_uncapped','efficiency_margin'}
    if mandatory-set(a):raise ValueError(f'Missing candidate columns {mandatory-set(a)}')
    if not {'home_only_margin','efficiency_margin','forecast_cutoff_utc'}.issubset(b):raise ValueError('Missing historical efficiency fields')
    j=a.merge(b[['game_id','home_only_margin','efficiency_margin','forecast_cutoff_utc']],on='game_id',validate='one_to_one',suffixes=('','_hist'))
    if j.empty:raise ValueError('No matched historical games')
    j['date']=pd.to_datetime(j.date,utc=True,errors='coerce')
    for col in ('forecast_cutoff_utc','forecast_cutoff_utc_hist'):
        j[col]=pd.to_datetime(j[col],utc=True,errors='coerce')
    if j[['date','forecast_cutoff_utc','forecast_cutoff_utc_hist']].isna().any().any():raise ValueError('Missing date or forecast cutoff')
    if (j.forecast_cutoff_utc>j.date).any() or (j.forecast_cutoff_utc_hist>j.date).any():raise ValueError('Future-data leakage')
    if not np.allclose(j.efficiency_margin,j.efficiency_margin_hist,rtol=0,atol=0.0002):raise ValueError('Historical efficiency forecast mismatch')
    if not j.neutral_site.astype(str).str.lower().isin(('true','false')).all():raise ValueError('Missing venue verification')
    j['neutral']=j.neutral_site.astype(str).str.lower().eq('true')
    for col in ('home_points','away_points','on_court_proxy_margin','cap_uncapped','efficiency_margin','home_only_margin'):
        j[col]=pd.to_numeric(j[col],errors='coerce')
    if j[list(('home_points','away_points','on_court_proxy_margin','cap_uncapped','efficiency_margin','home_only_margin'))].isna().any().any():raise ValueError('Missing paired values')
    j['actual']=j.home_points-j.away_points
    j['base_efficiency']=j.efficiency_margin-j.home_only_margin
    return j

def fit_location(train, ridge=20.0):
    """Ridge-fit [neutral intercept, non-neutral increment] to pregame signed residuals."""
    if len(train)<200 or train.neutral.sum()<15 or (~train.neutral).sum()<100:raise ValueError('Insufficient historical training/venue coverage')
    y=(train.actual-train.base_efficiency).to_numpy(float)
    x=np.column_stack((np.ones(len(train)), (~train.neutral).astype(float).to_numpy()))
    # Shrink intercept modestly, incremental location effect more strongly.
    ridge_mat=np.diag((ridge,ridge))
    coefficients=np.linalg.solve(x.T@x+ridge_mat,x.T@y)
    return {'neutral_intercept':float(coefficients[0]),'additional_home_effect':float(coefficients[1]),'train_games':int(len(train)),'train_neutral':int(train.neutral.sum())}

def predict(df,parameters):
    home=(~df.neutral).astype(float).to_numpy()
    fixed=df.base_efficiency.to_numpy(float)+parameters['neutral_intercept']+home*parameters['additional_home_effect']
    power=df.cap_uncapped.to_numpy(float)
    heavy=np.abs(power)>=12
    return {'capped_power':df.on_court_proxy_margin.to_numpy(float), 'uncapped_power':power,
            'v85_efficiency':df.efficiency_margin.to_numpy(float), 'venue_corrected_efficiency':fixed,
            'blend10':.9*power+.1*fixed,'blend25':.75*power+.25*fixed,
            'conditional12_50':np.where(heavy,.5*power+.5*fixed,power)}

def metrics(actual,pred):
    a=np.asarray(actual,float);p=np.asarray(pred,float)
    good=(a!=0)&(p!=0)
    return {'games':int(len(a)),'mae':round(float(np.mean(np.abs(a-p))),4),
            'winner_accuracy':round(float(np.mean((a[good]>0)==(p[good]>0))),4) if good.any() else None,
            'bias_actual_minus_pred':round(float(np.mean(a-p)),4)}

def evaluate(df,params, label):
    forecast=predict(df,params)
    out={'season':label,'games':int(len(df)),'overall':{k:metrics(df.actual.values,v) for k,v in forecast.items()},'by_venue':{},'by_spread':{}}
    for name,mask in (('neutral',df.neutral.to_numpy()),('non_neutral',(~df.neutral).to_numpy())):
        if mask.any():out['by_venue'][name]={k:metrics(df.actual.values[mask],v[mask]) for k,v in forecast.items()}
    buckets=pd.cut(np.abs(df.cap_uncapped.values),[-.01,3,7,12,20,np.inf],labels=['0-3','3-7','7-12','12-20','20+'])
    for lab in buckets.unique():
        mask=np.asarray(buckets==lab)
        if mask.any():out['by_spread'][str(lab)]={k:metrics(df.actual.values[mask],v[mask]) for k,v in forecast.items()}
    # Paired MAE deltas and simple 95% game-resampling percentile CI, no model selection.
    rng=np.random.default_rng(94)
    if len(df)>30:
        baseline=np.abs(df.actual.values-forecast['uncapped_power'])
        out['paired_mae_vs_uncapped']={}
        for name in ('venue_corrected_efficiency','blend10','blend25','conditional12_50'):
            dif=np.abs(df.actual.values-forecast[name])-baseline
            idx=rng.integers(0,len(dif),size=(750,len(dif)))
            ci=np.quantile(dif[idx].mean(axis=1),[.025,.975])
            out['paired_mae_vs_uncapped'][name]={'delta_mae':round(float(dif.mean()),4),'naive_game_bootstrap_95pct_interval':[round(float(x),4) for x in ci]}
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('--train-candidates',required=True);p.add_argument('--train-efficiency',required=True)
    p.add_argument('--holdout-candidates',required=True);p.add_argument('--holdout-efficiency',required=True)
    p.add_argument('--division',choices=('mens','womens'),required=True);p.add_argument('--out',required=True)
    a=p.parse_args();kw={'dtype':{'game_id':str,'home_id':str,'away_id':str}}
    old=prepare(pd.read_csv(a.train_candidates,**kw),pd.read_csv(a.train_efficiency,**kw))
    hold=prepare(pd.read_csv(a.holdout_candidates,**kw),pd.read_csv(a.holdout_efficiency,**kw))
    if not old.date.dt.strftime('%Y-%m').between('2025-11','2026-04').all():raise ValueError('Training season must be 2025-26')
    if not hold.date.dt.strftime('%Y-%m').between('2024-11','2025-04').all():raise ValueError('Holdout season must be 2024-25')
    early=old[old.date<SPLIT].copy();later=old[old.date>=SPLIT].copy()
    if later.empty:raise ValueError('No later-season evaluation games')
    params=fit_location(early)
    result={'status':'RESEARCH_ONLY_VENUE_AWARE_POSTPROCESSOR','division':a.division,
            'note':'Removes empirical V85 home-margin add-on, then ridge-fits neutral baseline and incremental home effect on 2025-26 pre-Feb games only. This does NOT refit the efficiency possession model or reproduce production preseason priors.',
            'parameters':params, 'train_before':str(SPLIT.date()),
            'development_later_2025_26':evaluate(later,params,'2025-26 after Jan 31'),
            'frozen_transfer_2024_25':evaluate(hold,params,'2024-25'),
            'statistical_note':'Bootstrap intervals resample games independently; same-team/time dependence can make them too narrow. 2024-25 is earlier than training, so this is transferability research, not a chronologically deployable test.'}
    dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'division':a.division,'status':result['status'],'parameters':params,'2024-25':result['frozen_transfer_2024_25']['overall']},indent=2))
if __name__=='__main__':main()

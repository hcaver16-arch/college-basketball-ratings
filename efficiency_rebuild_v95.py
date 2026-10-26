"""V95 research-only possession-aware efficiency margin reconstruction.

Same two-way ridge structure as adjusted_efficiency.fit_adjusted_efficiency:
points per 100 = mean + attack_team - defense_opponent + home_indicator*home_edge.
Unlike V85, use fitted home effect in points/100, not a second empirical point-margin add-on.
No official forecast files are modified.
"""
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

SPLIT=pd.Timestamp('2026-02-01',tz='UTC')

def validate(games, venues):
    needed={'game_id','date','home_id','away_id','home_points','away_points','possessions'}
    if needed-set(games): raise ValueError(f'Missing games fields: {needed-set(games)}')
    v=venues.copy(); g=games.copy()
    for frame in (g,v):
        frame['game_id']=frame.game_id.astype(str).str.strip()
        if frame.game_id.duplicated().any(): raise ValueError('Duplicate game IDs')
    for c in ('home_id','away_id'):
        g[c]=g[c].astype(str).str.strip()
        if c in v: v[c]=v[c].astype(str).str.strip()
    if not {'neutral_site','neutral_verified'}.issubset(v):raise ValueError('Missing venue verification')
    v['neutral_verified']=v.neutral_verified.astype(str).str.lower().eq('true')
    v['neutral_site']=v.neutral_site.astype(str).str.lower()
    v=v[v.neutral_verified]
    if not v.neutral_site.isin(('true','false')).all():raise ValueError('Invalid neutral-site flags')
    g=g.merge(v[['game_id','neutral_site']+([c for c in ('home_id','away_id') if c in v])],on='game_id',how='inner',suffixes=('','_venue'),validate='one_to_one')
    for c in ('home_id','away_id'):
        if f'{c}_venue' in g and not (g[c]==g[f'{c}_venue']).all():raise ValueError('Venue/game team mismatch')
    g['neutral_site']=g.neutral_site.eq('true')
    g['date']=pd.to_datetime(g.date,utc=True,errors='coerce')
    for c in ('home_points','away_points','possessions'):g[c]=pd.to_numeric(g[c],errors='coerce')
    g=g.dropna(subset=['date','home_points','away_points','possessions'])
    g=g[g.possessions.between(35,120)&g.home_points.between(0,200)&g.away_points.between(0,200)&(g.home_id!=g.away_id)]
    return g.sort_values(['date','game_id']).reset_index(drop=True)

def fit_snapshot(train,prior_games=8,min_games=3):
    if len(train)<30:return None
    ids=sorted(set(train.home_id)|set(train.away_id));n=len(ids); idx={v:i for i,v in enumerate(ids)}
    x=np.zeros((2*len(train),2*n+2));y=np.zeros(2*len(train));counts=np.zeros(n,int)
    for i,r in enumerate(train.itertuples(index=False)):
        h,a=idx[r.home_id],idx[r.away_id];counts[h]+=1;counts[a]+=1;j=2*i
        x[j,0]=1;x[j,1+h]=1;x[j,1+n+a]=-1;x[j,-1]=0 if r.neutral_site else 1
        x[j+1,0]=1;x[j+1,1+a]=1;x[j+1,1+n+h]=-1
        y[j]=100*r.home_points/r.possessions;y[j+1]=100*r.away_points/r.possessions
    penalty=np.full(2*n+2,float(prior_games));penalty[0]=0;penalty[-1]=24
    sol=np.linalg.solve(x.T@x+np.diag(penalty),x.T@y)
    baseline=sol[0];o=baseline+sol[1:1+n];d=baseline+sol[1+n:1+2*n]
    return {'ratings':{tid:(float(o[i]),float(d[i])) for tid,i in idx.items() if counts[i]>=min_games},
            'home_effect_per100':float(sol[-1]),'training_games':len(train),'training_neutral_games':int(train.neutral_site.sum())}

def predict_historical(games,step_days=7,warmup_days=28):
    if games.empty:return pd.DataFrame()
    rows=[];start=games.date.min()+pd.Timedelta(days=warmup_days);end=games.date.max()+pd.Timedelta(days=1)
    at=start
    while at<end:
        stop=min(at+pd.Timedelta(days=step_days),end)
        train=games[games.date<at].tail(5000)
        tests=games[(games.date>=at)&(games.date<stop)]
        if not tests.empty:
            model=fit_snapshot(train)
            if model:
                rated=model['ratings'];p=float(train.possessions.mean());home=model['home_effect_per100']
                for r in tests.itertuples(index=False):
                    if r.home_id not in rated or r.away_id not in rated:continue
                    ho,hd=rated[r.home_id];ao,ad=rated[r.away_id]
                    neutral_margin=((ho-ad)-(ao-hd))*p/100
                    home_margin=(0 if r.neutral_site else home*p/100)
                    rows.append({'game_id':r.game_id,'date':r.date.isoformat(),'forecast_cutoff_utc':at.isoformat(),
                                 'home_id':r.home_id,'away_id':r.away_id,'actual_margin':float(r.home_points-r.away_points),
                                 'neutral_site':bool(r.neutral_site),'pred_margin':neutral_margin+home_margin,
                                 'neutral_margin':neutral_margin,'home_effect_points':home_margin,
                                 'fitted_home_effect_per100':home,'expected_possessions':p,'train_games':len(train),
                                 'training_neutral_games':model['training_neutral_games']})
        at=stop
    return pd.DataFrame(rows)

def attach_candidates(rebuilt,candidate_path):
    c=pd.read_csv(candidate_path,dtype={'game_id':str});
    if c.game_id.duplicated().any():raise ValueError('Duplicate candidate game IDs')
    required={'game_id','cap_uncapped','on_court_proxy_margin','efficiency_margin','forecast_cutoff_utc'}
    if required-set(c):raise ValueError(f'Missing candidate columns {required-set(c)}')
    d=rebuilt.merge(c[list(required)],on='game_id',validate='one_to_one',how='inner',suffixes=('','_candidate'))
    if d.empty:raise ValueError('No same-game overlap with V91 archive')
    cut=pd.to_datetime(d.forecast_cutoff_utc_candidate,utc=True,errors='coerce');date=pd.to_datetime(d.date,utc=True)
    if cut.isna().any() or (cut>date).any():raise ValueError('Candidate forecast uses future data')
    if not (pd.to_datetime(d.forecast_cutoff_utc,utc=True)<=date).all():raise ValueError('Rebuilt forecast uses future data')
    return d

def metric(a,p):
    a=np.asarray(a,float);p=np.asarray(p,float);keep=(a!=0)&(p!=0)
    return {'games':int(len(a)),'mae':round(float(np.mean(np.abs(a-p))),4),
            'winner_accuracy':round(float(np.mean(np.sign(a[keep])==np.sign(p[keep]))),4) if keep.any() else None,
            'signed_bias':round(float(np.mean(a-p)),4)}

def report(d):
    if d.empty:raise ValueError('No evaluable games')
    a=d.actual_margin.to_numpy(float);power=d.cap_uncapped.to_numpy(float);new=d.pred_margin.to_numpy(float)
    forecasts={'capped_power':d.on_court_proxy_margin.to_numpy(float),'uncapped_power':power,
               'v85_efficiency':d.efficiency_margin.to_numpy(float),'rebuilt_efficiency':new,
               'blend10_rebuilt':.9*power+.1*new,'blend25_rebuilt':.75*power+.25*new,
               'conditional12_50_rebuilt':np.where(np.abs(power)>=12,.5*power+.5*new,power)}
    out={'games':len(d),'overall':{k:metric(a,v) for k,v in forecasts.items()},'by_venue':{},'by_spread':{}}
    for label,mask in [('neutral',d.neutral_site.to_numpy(bool)),('non_neutral',~d.neutral_site.to_numpy(bool))]:
        if mask.any():out['by_venue'][label]={k:metric(a[mask],v[mask]) for k,v in forecasts.items()}
    for lab,left,right in [('0-3',0,3),('3-7',3,7),('7-12',7,12),('12-20',12,20),('20+',20,float('inf'))]:
        ab=np.abs(power);mask=(ab>=left)&(ab<right)
        if mask.any():out['by_spread'][lab]={k:metric(a[mask],v[mask]) for k,v in forecasts.items()}
    rng=np.random.default_rng(95);base=np.abs(a-power)
    out['paired_mae_deltas']={}
    for key in ('rebuilt_efficiency','blend10_rebuilt','blend25_rebuilt','conditional12_50_rebuilt'):
        diff=np.abs(a-forecasts[key])-base
        # Resample complete dates instead of games, to partially account for within-day correlation.
        dates=pd.to_datetime(d.date,utc=True).dt.strftime('%Y-%m-%d').to_numpy()
        unique=np.unique(dates);perday=np.array([diff[dates==day].sum() for day in unique]);counts=np.array([(dates==day).sum() for day in unique])
        samples=rng.integers(0,len(unique),size=(500,len(unique)))
        boot=perday[samples].sum(axis=1)/counts[samples].sum(axis=1)
        out['paired_mae_deltas'][key]={'delta_vs_uncapped':round(float(diff.mean()),4),
            'date_cluster_bootstrap_95pct':[round(float(t),4) for t in np.quantile(boot,[.025,.975])]}
    return out

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--games',required=True);parser.add_argument('--venues',required=True)
    parser.add_argument('--candidates',required=True);parser.add_argument('--division',choices=['mens','womens'],required=True)
    parser.add_argument('--season',choices=['2024-25','2025-26'],required=True);parser.add_argument('--out-dir',required=True)
    args=parser.parse_args();raw=pd.read_csv(args.games,dtype={'game_id':str,'home_id':str,'away_id':str});venue=pd.read_csv(args.venues,dtype={'game_id':str,'home_id':str,'away_id':str})
    g=validate(raw,venue)
    if not g.date.dt.strftime('%Y-%m').between(args.season[:4]+'-11',str(int(args.season[:4])+1)+'-04').all():
        raise ValueError('Season dates mismatch')
    pred=predict_historical(g)
    d=attach_candidates(pred,args.candidates)
    if args.season=='2025-26':d=d[pd.to_datetime(d.date,utc=True)>=SPLIT].copy()
    else:d=d[pd.to_datetime(d.date,utc=True)>=pd.Timestamp('2025-02-01',tz='UTC')].copy()
    if d.empty:raise ValueError('No post-Jan evaluation games')
    result={'status':'RESEARCH_ONLY_REBUILT_POSSESSION_MODEL','division':args.division,'season':args.season,
            'warning':'2024-25 previously examined; neither season remains a pristine unseen holdout. On-court proxy lacks historical preseason priors. No production selection.',
            'method':'Two-way regularized offense-defense fit; fitted non-neutral home effect in points per 100 converted to points using past mean possessions; strictly earlier weekly snapshots. Refit each season only from its own past games; no cross-season coefficients.',
            'evaluation':report(d)}
    dest=Path(args.out_dir);dest.mkdir(parents=True,exist_ok=True)
    d.to_csv(dest/'matched_forecasts.csv.gz',index=False,compression='gzip')
    (dest/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'division':args.division,'season':args.season,'evaluation':result['evaluation']['overall']},indent=2))
if __name__=='__main__':main()

"""V91 research-only spread calibration and margin-cap sensitivity.

Input: verified paired games, ESPN venue audit and V90 pregame same-game forecasts.
NOT a live model change. All scenarios are exploratory and evaluated on 2025-26.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

CAPS = (30, 60, None)
BUCKETS = [0, 3, 7, 12, 20, float('inf')]
LABELS = ['0-3', '3-7', '7-12', '12-20', '20+']


def _quality(df):
    d = df.copy()
    for col in ('game_id', 'home_id', 'away_id'):
        d[col] = d[col].astype('string').str.strip()
    d['date'] = pd.to_datetime(d['date'], utc=True, errors='coerce')
    for col in ('home_points', 'away_points'):
        d[col] = pd.to_numeric(d[col], errors='coerce')
    d = d.dropna(subset=['date', 'home_points', 'away_points', 'home_id', 'away_id', 'game_id'])
    d = d[(d.home_id != d.away_id) & d.home_points.between(0, 200) & d.away_points.between(0, 200)].copy()
    if d.game_id.duplicated().any():
        raise ValueError('Duplicate historical game IDs')
    return d.sort_values(['date', 'game_id']).reset_index(drop=True)


def _ratings(train, cap):
    """Same regularized Laplacian as rating_engine.calculate_power, adjustable clip."""
    if len(train) < 20:
        return {}
    teams = sorted(set(train.home_id) | set(train.away_id))
    ix = {tid: i for i, tid in enumerate(teams)}
    n = len(teams)
    mat = np.zeros((n, n), dtype=float)
    vec = np.zeros(n, dtype=float)
    for g in train.itertuples(index=False):
        hi, ai = ix[g.home_id], ix[g.away_id]
        raw = float(g.home_points - g.away_points)
        diff = float(np.clip(raw, -cap, cap)) if cap is not None else raw
        val = diff - (0. if g.neutral_site else 3.)
        mat[hi, hi] += 1; mat[ai, ai] += 1
        mat[hi, ai] -= 1; mat[ai, hi] -= 1
        vec[hi] += val; vec[ai] -= val
    fit = np.linalg.solve(mat + 8. * np.eye(n), vec)
    fit -= np.mean(fit)
    # Critical reproducibility note: original engine rounds powers to 2 decimals.
    fit = np.round(fit, 2)
    return dict(zip(teams, fit))


def _stats(df, pred):
    if df.empty: return {'games': 0, 'mae': None, 'winner_accuracy': None, 'bias_actual_minus_pred': None}
    actual = df['actual_margin'].to_numpy(float)
    forecast = np.asarray(pred, dtype=float)
    eligible = (actual != 0) & (forecast != 0)
    return {'games': int(len(df)), 'mae': round(float(np.abs(actual-forecast).mean()), 4),
            'winner_accuracy': round(float(np.mean((actual[eligible]>0)==(forecast[eligible]>0))), 4) if eligible.any() else None,
            'bias_actual_minus_pred': round(float(np.mean(actual-forecast)), 4)}


def experiment(games, venues, predictions):
    g = _quality(games)
    v = venues.copy()
    for col in ('game_id','home_id','away_id'): v[col] = v[col].astype('string').str.strip()
    if v.game_id.duplicated().any(): raise ValueError('Duplicate venues')
    v['neutral_verified'] = v.neutral_verified.astype(str).str.lower().eq('true')
    v['neutral_site'] = v.neutral_site.astype(str).str.lower().eq('true')
    joined = g.merge(v[['game_id','home_id','away_id','neutral_verified','neutral_site']], on='game_id', how='left', validate='one_to_one', suffixes=('','_venue'))
    conflict = joined.neutral_verified.fillna(False) & ((joined.home_id!=joined.home_id_venue)|(joined.away_id!=joined.away_id_venue))
    if conflict.any(): raise ValueError('Verified venue IDs do not match games')
    g = joined[joined.neutral_verified.fillna(False)].copy()
    p = predictions.copy()
    for col in ('game_id','home_id','away_id'): p[col] = p[col].astype('string').str.strip()
    p['cutoff'] = pd.to_datetime(p.forecast_cutoff_utc, utc=True, errors='coerce')
    if p.game_id.duplicated().any(): raise ValueError('Duplicate forecast IDs')
    required = ['game_id','home_id','away_id','forecast_cutoff_utc','efficiency_margin','on_court_proxy_margin']
    for col in required:
        if col not in p: raise ValueError(f'Missing V90 prediction column: {col}')
    x = g.merge(p[required+['cutoff']], on='game_id', how='inner',validate='one_to_one',suffixes=('','_forecast'))
    if x.empty: return pd.DataFrame(), {'status': 'NO_MATCHED_GAMES'}
    if not ((x.home_id==x.home_id_forecast)&(x.away_id==x.away_id_forecast)).all():raise ValueError('Game/forecast team mismatch')
    if (x.cutoff.isna()|(x.cutoff>x.date)).any():raise ValueError('Forecast cutoff missing or after game start')
    # V90 creates the original forecasts without future-data leakage. We refit
    # all cap scenarios on the exact same verified pre-cutoff games.
    generated=[]
    for cutoff,batch in x.groupby('cutoff',sort=True):
        train = g[g.date<cutoff]
        cap_tables = {cap: _ratings(train,cap) for cap in CAPS}
        for row in batch.itertuples(index=False):
            record={'game_id':row.game_id}
            for cap,table in cap_tables.items():
                name = 'uncapped' if cap is None else str(cap)
                if row.home_id not in table or row.away_id not in table:
                    record[f'cap_{name}'] = np.nan
                else:
                    record[f'cap_{name}']=float(table[row.home_id]-table[row.away_id]+(0 if row.neutral_site else 3))
            generated.append(record)
    x = x.merge(pd.DataFrame(generated),on='game_id',validate='one_to_one')
    x['actual_margin']=x.home_points-x.away_points
    x['abs_baseline_spread']=x.on_court_proxy_margin.abs()
    x['spread_bucket']=pd.cut(x.abs_baseline_spread,BUCKETS,labels=LABELS,include_lowest=True)
    x['month']=x.date.dt.strftime('%Y-%m')
    # Exploratory *predefined* rules. Do not choose best based on this same season.
    # For big spreads use efficiency fraction x; otherwise original power proxy.
    for threshold in (12,20):
        for weight in (0.25,0.5,0.75,1.0):
            col=f'blend_ge{threshold}_eff{int(weight*100)}'
            x[col]=np.where(x.abs_baseline_spread>=threshold,
                            (1-weight)*x.on_court_proxy_margin+weight*x.efficiency_margin,
                            x.on_court_proxy_margin)
    candidates=['on_court_proxy_margin','efficiency_margin','cap_30','cap_60','cap_uncapped']+[c for c in x if c.startswith('blend_ge')]
    report={'status':'EXPLORATORY_RESEARCH_NOT_VALIDATED','matched_games':int(len(x)),
            'warning':'All candidate variants evaluated on the discovery season (2025-26), not an independent holdout. No automatic model selection or production changes.',
            'data_note':'Venue-verified paired games only. On-court proxy omits preseason priors and blending.',
            'overall':{},'by_baseline_spread':{},'by_month':{},'by_venue':{},'signed_spread_bias':{}}
    for col in candidates:
        subset=x[x[col].notna()]
        report['overall'][col]=_stats(subset,subset[col])
    for name, d in x.groupby('spread_bucket',observed=True):
        report['by_baseline_spread'][str(name)]={col:_stats(d[d[col].notna()],d.loc[d[col].notna(),col]) for col in ('on_court_proxy_margin','efficiency_margin','cap_30','cap_60','cap_uncapped','blend_ge12_eff50','blend_ge20_eff50')}
        # Does baseline underestimate the *magnitude* of the projected favorite's win?
        sign=np.sign(d.on_court_proxy_margin.to_numpy(float))
        actual_signed=sign*d.actual_margin.to_numpy(float)
        predicted_mag=np.abs(d.on_court_proxy_margin.to_numpy(float))
        report['signed_spread_bias'][str(name)]={'games':int(len(d)),
            'mean_predicted_favorite_margin':round(float(predicted_mag.mean()),3),
            'mean_actual_favorite_margin':round(float(actual_signed.mean()),3),
            'actual_minus_predicted_favorite_margin':round(float(np.mean(actual_signed-predicted_mag)),3)}
    for month,d in x.groupby('month'):
        report['by_month'][str(month)]={k:_stats(d[d[k].notna()],d.loc[d[k].notna(),k]) for k in ('on_court_proxy_margin','efficiency_margin','cap_30','cap_60','cap_uncapped','blend_ge12_eff50','blend_ge20_eff50')}
    for flag,d in x.groupby('neutral_site'):
        report['by_venue']['neutral' if flag else 'home']={k:_stats(d[d[k].notna()],d.loc[d[k].notna(),k]) for k in ('on_court_proxy_margin','efficiency_margin','cap_30','cap_60','cap_uncapped')}
    return x,report


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--games',required=True);ap.add_argument('--venues',required=True)
    ap.add_argument('--predictions',required=True);ap.add_argument('--out',required=True)
    a=ap.parse_args()
    read_kw={'dtype':{'game_id':str,'home_id':str,'away_id':str}}
    result,report=experiment(pd.read_csv(a.games,**read_kw),pd.read_csv(a.venues,**read_kw),pd.read_csv(a.predictions,**read_kw))
    dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
    (dest/'blowout_research_summary.json').write_text(json.dumps(report,indent=2)+'\n')
    if not result.empty:
        result.to_csv(dest/'candidate_game_predictions.csv.gz',compression='gzip',index=False)
        result['baseline_abs_error']=(result.actual_margin-result.on_court_proxy_margin).abs()
        result.nlargest(100,'baseline_abs_error').to_csv(dest/'largest_misses.csv',index=False)
    print(json.dumps({'status':report['status'],'matched_games':report.get('matched_games'),
                      'overall':report.get('overall',{}),'signed_spread_bias':report.get('signed_spread_bias',{})},indent=2))

if __name__=='__main__':main()

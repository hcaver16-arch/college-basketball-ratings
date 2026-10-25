"""V89 research-only same-game comparison: original Courtside on-court rating math.

IMPORTANT: 2025-26 prior-season ratings (2024-25) and their roster effects are
not supplied. This reproduces calculate_power, NOT the full blended production
Current power model. Outputs are labelled 'on_court_proxy' throughout.
"""
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from rating_engine import calculate_power


def prepare(games):
    needed={'game_id','date','home_id','away_id','home_points','away_points'}
    missing=needed-set(games.columns)
    if missing: raise ValueError(f'Historical games missing {sorted(missing)}')
    x=games.copy()
    for c in ['game_id','home_id','away_id']:
        x[c]=x[c].astype('string').str.strip()
    x['date']=pd.to_datetime(x.date,utc=True,errors='coerce')
    for c in ['home_points','away_points']:
        x[c]=pd.to_numeric(x[c],errors='coerce')
    x=x.dropna(subset=list(needed))
    x=x[x.home_id.ne(x.away_id) & x.home_points.between(0,200) & x.away_points.between(0,200)]
    if x.game_id.duplicated().any(): raise ValueError('Duplicate IDs in games input')
    return x.sort_values(['date','game_id']).reset_index(drop=True)


def score(df,column):
    if df.empty:return {'games':0}
    actual=df.home_points-df.away_points
    pred=df[column]
    ties=actual.ne(0)&pred.ne(0)
    return {'games':int(len(df)), 'margin_mae':round(float((actual-pred).abs().mean()),3),
            'winner_accuracy_excluding_ties':round(float(((actual[ties]>0)==(pred[ties]>0)).mean()),4) if ties.any() else None}


def evaluate(games, eff, *, step_days=7):
    games=prepare(games)
    if eff.empty:return pd.DataFrame(),{'status':'NO_EFFICIENCY_FORECASTS'}
    eff=eff.copy()
    for c in ('game_id','home_id','away_id'):
        if c in eff: eff[c]=eff[c].astype('string').str.strip()
    if 'efficiency_margin' not in eff.columns:raise ValueError('Missing efficiency_margin')
    if 'forecast_cutoff_utc' not in eff.columns:raise ValueError('Missing forecast_cutoff_utc')
    eff['cutoff']=pd.to_datetime(eff.forecast_cutoff_utc,utc=True,errors='coerce')
    if eff.game_id.duplicated().any():raise ValueError('Duplicate efficiency game IDs')
    merged=games.merge(eff[['game_id','home_id','away_id','efficiency_margin','cutoff','training_max_date']],on='game_id',suffixes=('','_eff'),how='inner',validate='one_to_one')
    if merged.empty:return pd.DataFrame(),{'status':'NO_MATCHING_GAMES','historical_games':len(games),'efficiency_forecasts':len(eff)}
    if not ((merged.home_id==merged.home_id_eff)&(merged.away_id==merged.away_id_eff)).all():raise ValueError('Team IDs mismatch on matched game')
    if (merged.cutoff.isna() | (merged.cutoff>merged.date)).any():raise ValueError('Invalid efficiency forecast cutoffs')
    merged['training_max_date']=pd.to_datetime(merged.training_max_date,utc=True,errors='coerce')
    if (merged.training_max_date.isna() | (merged.training_max_date>=merged.cutoff)).any():raise ValueError('Efficiency training cutoff leakage')
    rows=[]
    # Crucial: reconstruct on each ORIGINAL forecast cutoff. All training game dates < cutoff.
    for cutoff,batch in merged.groupby('cutoff',sort=True):
        prior=games[games.date<cutoff]
        training=pd.DataFrame({
            'Game ID':prior.game_id.astype(str),'Status':'Final',
            'Home ID':prior.home_id.astype(str),'Away ID':prior.away_id.astype(str),
            'Home':prior.home_id.astype(str),'Away':prior.away_id.astype(str),
            'Home score':prior.home_points,'Away score':prior.away_points,'Venue':'Home'})
        # Paired efficiency dataset lacks neutral-site flag: marked Home here.
        # Run original calculate_power unchanged (ridge 8, capped +/-40, 3pt HCA).
        ratings,_=calculate_power(training)
        table=ratings.set_index('Team ID')['Power'].to_dict()
        for g in batch.itertuples(index=False):
            home=str(g.home_id);away=str(g.away_id)
            if home not in table or away not in table:continue
            proxy=float(table[home]-table[away]+3.)
            rows.append({'game_id':str(g.game_id),'date':g.date.isoformat(),'forecast_cutoff_utc':cutoff.isoformat(),
                         'home_id':home,'away_id':away,'home_points':float(g.home_points),'away_points':float(g.away_points),
                         'efficiency_margin':float(g.efficiency_margin),'on_court_proxy_margin':proxy,
                         'equal_blend_margin':(float(g.efficiency_margin)+proxy)/2,
                         'training_max_date':prior.date.max().isoformat() if len(prior) else '',
                         'train_games':len(prior)})
    result=pd.DataFrame(rows)
    summary={'status':'RESEARCH_PROXY_COMPARISON' if len(result) else 'NO_MATCHED_RATED_GAMES',
             'matched_games':len(result),'eligible_efficiency_games':len(merged),
             'data_note':'Uses original rating_engine.calculate_power; omits 2024-25 preseason priors and blending; assumes all games home site because paired archive lacks neutral flag; not official Courtside reconstruction.',
             'efficiency':score(result,'efficiency_margin'),'on_court_proxy':score(result,'on_court_proxy_margin'),
             'equal_blend_exploratory':score(result,'equal_blend_margin')}
    if not result.empty:
        result['month']=pd.to_datetime(result.date).dt.strftime('%Y-%m')
        summary['by_month']={month:{model:score(df,col) for model,col in [('efficiency','efficiency_margin'),('on_court_proxy','on_court_proxy_margin'),('blend','equal_blend_margin')]} for month,df in result.groupby('month')}
    return result,summary


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--games',required=True)
    ap.add_argument('--efficiency',required=True)
    ap.add_argument('--out',required=True)
    a=ap.parse_args()
    g=pd.read_csv(a.games,dtype={'game_id':str,'home_id':str,'away_id':str})
    e=pd.read_csv(a.efficiency,dtype={'game_id':str,'home_id':str,'away_id':str})
    result,summary=evaluate(g,e)
    p=Path(a.out);p.mkdir(parents=True,exist_ok=True)
    result.to_csv(p/'same_game_reconstructed_predictions.csv',index=False)
    (p/'comparison_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()

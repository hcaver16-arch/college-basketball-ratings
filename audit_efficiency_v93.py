"""Audit V85 prediction conversion using existing same-game V91 dataset and V85 forecasts.
V85's home_only_margin is its estimated mean home margin; this audit subtracts that
term rather than pretending to know the fitted efficiency-model home effect.
Ablation is a diagnostic, NOT a replacement forecast or corrected neutral adjustment.
"""
import argparse,json
from pathlib import Path
import pandas as pd
import numpy as np

def audit(candidates, history):
    a=candidates.copy();h=history.copy()
    for df in (a,h):
        df['game_id']=df.game_id.astype(str)
        if df.game_id.duplicated().any():raise ValueError('Duplicate game ID')
    if 'home_only_margin' not in h or 'efficiency_margin' not in a:raise ValueError('Missing V85 home_only_margin / V91 efficiency_margin')
    d=a.merge(h[['game_id','home_only_margin','efficiency_margin','forecast_cutoff_utc']],on='game_id',how='inner',suffixes=('','_v85'),validate='one_to_one')
    if d.empty:raise ValueError('No matching games')
    d['date']=pd.to_datetime(d.date,utc=True); d['cutoff']=pd.to_datetime(d.forecast_cutoff_utc,utc=True)
    d['cutoff_v85']=pd.to_datetime(d.forecast_cutoff_utc_v85,utc=True)
    if (d.cutoff>d.date).any() or (d.cutoff_v85>d.date).any():raise ValueError('Future-date leakage')
    if not np.allclose(d.efficiency_margin,d.efficiency_margin_v85,atol=.0001):raise ValueError('V85/V91 efficiency margins differ')
    actual=d.home_points-d.away_points
    original=d.efficiency_margin
    ablation=original-d.home_only_margin
    neutral=d.neutral_site.astype(str).str.lower().eq('true')
    def summarize(sel):
        x=actual[sel];o=original[sel];z=ablation[sel]
        return {'games':len(x),'v85_mae':round(float(np.abs(x-o).mean()),4),'without_empirical_home_margin_mae':round(float(np.abs(x-z).mean()),4),
                'v85_signed_bias':round(float((x-o).mean()),4),'without_empirical_home_margin_signed_bias':round(float((x-z).mean()),4),
                'mean_empirical_home_margin_added':round(float(d.home_only_margin[sel].mean()),4)}
    return {'status':'EFFICIENCY_LOCATION_DIAGNOSTIC','note':'Ablation removes empirical home-margin addition from V85; does NOT estimate the correct home effect. Neutral games were also given this addition in V85.',
            'all':summarize(pd.Series(True,index=d.index)),'neutral':summarize(neutral),'non_neutral':summarize(~neutral)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidates',required=True);p.add_argument('--efficiency',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();r=audit(pd.read_csv(args.candidates,dtype={'game_id':str}),pd.read_csv(args.efficiency,dtype={'game_id':str}))
    dest=Path(args.out);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()

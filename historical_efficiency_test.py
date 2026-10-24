"""Leakage-safe exploratory historical evaluation of opponent-adjusted efficiency.

Input: one CSV of completed D1-v-D1 games with columns
 game_id,date,home_id,away_id,home_points,away_points,possessions
where date is ISO local game date, and possessions is a paired box-score estimate.
Only *prior dates* may contribute to training a forecast; games on the same date
are never used to forecast one another. No existing production data is changed.

Important: evaluation here uses simple efficiency-derived point margins, with a
home advantage fit using previous games. The provided adjusted-efficiency model
is exploratory and the resulting model is NOT a calibrated sportsbook projection.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from adjusted_efficiency import fit_adjusted_efficiency

REQUIRED = ['game_id','date','home_id','away_id','home_points','away_points','possessions']


def validate(raw):
    missing=set(REQUIRED)-set(raw.columns)
    if missing: raise ValueError(f'Missing required columns: {sorted(missing)}')
    x=raw[REQUIRED].copy()
    for c in ['game_id','home_id','away_id']: x[c]=x[c].astype('string').str.strip()
    x['date']=pd.to_datetime(x['date'],errors='coerce',utc=True)
    for c in ['home_points','away_points','possessions']: x[c]=pd.to_numeric(x[c],errors='coerce')
    x=x.dropna(subset=REQUIRED)
    x=x[(x['possessions'].between(35,120)) & x['home_points'].between(0,200) & x['away_points'].between(0,200)]
    x=x[x.home_id != x.away_id]
    if x.game_id.duplicated().any(): raise ValueError('Duplicate game_id rows: do not silently discard historical records')
    return x.sort_values(['date','game_id']).reset_index(drop=True)


def score(frame, prefix):
    if frame.empty:return {'games':0}
    actual=frame.home_points-frame.away_points
    predicted=frame[prefix]
    return {'games':int(len(frame)), 'margin_mae':round(float((actual-predicted).abs().mean()),3),
            'winner_accuracy_excluding_ties':round(float(((predicted>0)==(actual>0)).mean()),4)}


def run_backtest(games, *, warmup_days=28, step_days=7, min_team_games=3, min_league_games=30,
                 prior_games=8.0, max_training_games=5000):
    games=validate(games)
    if games.empty:return pd.DataFrame(),{'input_games':0,'status':'No valid completed games'}
    origin=games.date.min()
    start=origin+pd.Timedelta(days=warmup_days)
    last=games.date.max()+pd.Timedelta(days=1)
    rows=[]; evaluated=0; no_coverage=0
    # Date-scoped snapshots: strictly earlier games only. No retrospective future roster inputs.
    at=start
    while at < last:
        window_end=min(at+pd.Timedelta(days=step_days),last)
        train=games[games.date < at].tail(max_training_games).copy()
        test=games[(games.date>=at)&(games.date<window_end)].copy()
        if test.empty:
            at=window_end;continue
        if len(train)<min_league_games:
            no_coverage+=len(test);at=window_end;continue
        trained=fit_adjusted_efficiency(train,prior_games=prior_games,min_games=min_team_games,
                                        min_league_games=min_league_games)
        if trained.empty:
            no_coverage+=len(test);at=window_end;continue
        rated=trained.dropna(subset=['adj_o','adj_d']).set_index('Team ID')
        # A simple empirical pre-snapshot home margin; prevents using future outcomes.
        home_edge=float((train.home_points-train.away_points).mean())
        for rec in test.itertuples(index=False):
            hid,aid=str(rec.home_id),str(rec.away_id)
            if hid not in rated.index or aid not in rated.index:
                no_coverage+=1;continue
            h,a=rated.loc[hid],rated.loc[aid]
            # Project each side's points/100 possessions vs the opposing defense,
            # and convert the implied margin using *prior* mean possessions.
            h_eff=float(h.adj_o-a.adj_d)
            a_eff=float(a.adj_o-h.adj_d)
            pre_poss=float(train.possessions.mean())
            est_margin=(h_eff-a_eff)*pre_poss/100 + home_edge
            rows.append({'game_id':str(rec.game_id),'date':rec.date.isoformat(),
                         'forecast_cutoff_utc':at.isoformat(),
                         'home_id':hid,'away_id':aid,'home_points':float(rec.home_points),
                         'away_points':float(rec.away_points),'efficiency_margin':est_margin,
                         'home_only_margin':home_edge,'train_games':int(len(train)),
                         'home_games_used':int(h.games_used),'away_games_used':int(a.games_used),
                         'training_max_date':train.date.max().isoformat()})
            evaluated+=1
        at=window_end
    out=pd.DataFrame(rows)
    metrics={'input_games':int(len(games)),'evaluated_games':evaluated,'not_evaluable':no_coverage,
             'warmup_days':warmup_days,'step_days':step_days,'minimum_team_games':min_team_games,
             'minimum_league_games':min_league_games,
             'method':'Rolling date-frozen snapshots, previous-date games only; exploratory model',
             'efficiency':score(out,'efficiency_margin') if not out.empty else {'games':0},
             'home_only_baseline':score(out,'home_only_margin') if not out.empty else {'games':0},
             'warning':'No comparison to Courtside official baseline unless same-game pregame predictions are supplied. No wager/ROI validation.'}
    return out,metrics


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--input',required=True,help='Historical paired D1 final game CSV or .csv.gz')
    p.add_argument('--output-dir',default='data/efficiency_backtests')
    p.add_argument('--warmup-days',type=int,default=28)
    p.add_argument('--step-days',type=int,default=7)
    p.add_argument('--min-team-games',type=int,default=3)
    p.add_argument('--min-league-games',type=int,default=30)
    args=p.parse_args()
    if args.warmup_days<1 or args.step_days<1: p.error('Warmup and step days must be positive')
    path=Path(args.input)
    if not path.is_file():p.error(f'Input does not exist: {path}')
    results,summary=run_backtest(pd.read_csv(path),warmup_days=args.warmup_days,
              step_days=args.step_days,min_team_games=args.min_team_games,
              min_league_games=args.min_league_games)
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    results.to_csv(out/'historical_efficiency_predictions.csv',index=False)
    (out/'historical_efficiency_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()

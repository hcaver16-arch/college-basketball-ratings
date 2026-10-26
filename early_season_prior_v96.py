"""Courtside V96 research-only preseason prior / early-season forecast test.

Prior ratings: complete 2024-25 team outcomes, available before Nov 2025.
Current ratings: only 2025-26 results before each verified forecast cutoff.
Roster evidence: optional dated pre-season, source-backed per-team *rating delta*
provided by user; never downloaded retrospectively or silently imputed.
No production files are changed.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

SEASON_START = pd.Timestamp('2025-11-01', tz='UTC')
LATEST_PRESEASON = pd.Timestamp('2025-11-01', tz='UTC')
EVAL_END = pd.Timestamp('2026-02-01', tz='UTC')


def prepare_games(path, venues_path=None):
    d = pd.read_csv(path, dtype={'game_id':str,'home_id':str,'away_id':str})
    needed={'game_id','date','home_id','away_id','home_points','away_points'}
    if needed-set(d): raise ValueError('Missing columns: '+str(needed-set(d)))
    if d.game_id.duplicated().any(): raise ValueError('Duplicate game IDs')
    d['date']=pd.to_datetime(d.date,utc=True,errors='coerce')
    if d.date.isna().any(): raise ValueError('Invalid dates')
    for col in ['home_points','away_points']:
        d[col]=pd.to_numeric(d[col],errors='coerce')
    d=d.dropna(subset=['home_points','away_points'])
    if venues_path is not None:
        v=pd.read_csv(venues_path,dtype={'game_id':str,'home_id':str,'away_id':str})
        if v.game_id.duplicated().any():raise ValueError('Duplicate venue IDs')
        if not {'game_id','neutral_site','neutral_verified'}.issubset(v):raise ValueError('Venue verification fields missing')
        v=v[v.neutral_verified.astype(str).str.lower().eq('true')].copy()
        v['neutral_site']=v.neutral_site.astype(str).str.lower()
        if not v.neutral_site.isin(['true','false']).all():raise ValueError('Invalid venue value')
        for col in ['home_id','away_id']:
            if col in v:
                chk=d[['game_id',col]].merge(v[['game_id',col]],on='game_id',how='inner',suffixes=('','_verify'))
                if (chk[col]!=chk[col+'_verify']).any():raise ValueError('Venue team mismatch')
        d=d.drop(columns=['neutral_site','neutral_verified'],errors='ignore').merge(v[['game_id','neutral_site']],on='game_id',how='inner',validate='one_to_one')
        d['neutral_site']=d.neutral_site.eq('true')
    else:
        if 'neutral_site' not in d:raise ValueError('Verified venue file is required if games lack neutral_site')
        d['neutral_site']=d.neutral_site.astype(str).str.lower().eq('true')
    if (d.home_id==d.away_id).any():raise ValueError('Same home and away team')
    return d.sort_values(['date','game_id']).reset_index(drop=True)


def ridge_strength(g, cap=None, ridge=8.):
    ids=sorted(set(g.home_id)|set(g.away_id))
    if not ids:return {},{}
    n=len(ids);ix={t:i for i,t in enumerate(ids)}
    mat=np.eye(n)*ridge;rhs=np.zeros(n);counts=np.zeros(n,dtype=int)
    for r in g.itertuples(index=False):
        h=ix[r.home_id];a=ix[r.away_id]
        margin=float(r.home_points-r.away_points)
        if cap is not None: margin=float(np.clip(margin,-cap,cap))
        margin-=0 if r.neutral_site else 3.0
        mat[h,h]+=1;mat[a,a]+=1;mat[h,a]-=1;mat[a,h]-=1
        rhs[h]+=margin;rhs[a]-=margin
        counts[h]+=1;counts[a]+=1
    result=np.linalg.solve(mat,rhs);result-=result.mean()
    return {t:float(result[i]) for t,i in ix.items()},{t:int(counts[i]) for t,i in ix.items()}


def blend_weight(games):
    anchors=[(0,0),(5,.35),(10,.65),(15,.85),(20,.95),(25,1.)]
    for (g0,w0),(g1,w1) in zip(anchors,anchors[1:]):
        if games<=g1:return w0+(w1-w0)*(games-g0)/(g1-g0)
    return 1.


def roster_adjustments(path):
    if not path:return {}, {'status':'not_provided','eligible_teams':0}
    d=pd.read_csv(path,dtype={'team_id':str})
    cols={'team_id','rating_delta','source_url','evidence_date'}
    if cols-set(d):raise ValueError(f'Roster file needs columns {sorted(cols)}')
    if d.team_id.duplicated().any():raise ValueError('Duplicate roster team IDs')
    dt=pd.to_datetime(d.evidence_date,utc=True,errors='coerce')
    if dt.isna().any() or (dt>=LATEST_PRESEASON).any():raise ValueError('Roster evidence must predate Nov 1 2025')
    if not d.source_url.fillna('').str.startswith(('https://','http://')).all():raise ValueError('Roster evidence URL required')
    delta=pd.to_numeric(d.rating_delta,errors='coerce')
    if delta.isna().any() or (~np.isfinite(delta)).any() or (delta.abs()>6).any():
        raise ValueError('Roster rating_delta must be finite and within ±6 points')
    # Sourced dates show point-in-time availability, not that a user-supplied rating delta is empirically validated.
    return dict(zip(d.team_id,delta.astype(float))),{'status':'user_supplied_unverified_effects','eligible_teams':len(d), 'warning':'Evidence timestamps and URL format checked, but URL authenticity and point deltas NOT independently validated.'}


def score(actual,pred):
    actual=np.asarray(actual,float);pred=np.asarray(pred,float)
    mask=(actual!=0)&(pred!=0)
    return {'games':len(actual),'mae':round(float(np.mean(np.abs(actual-pred))),4),
            'winner_accuracy':round(float(np.mean(np.sign(actual[mask])==np.sign(pred[mask]))),4) if mask.any() else None,
            'bias_actual_minus_prediction':round(float(np.mean(actual-pred)),4)}


def run(prior_games,current_games,candidates,roster=None):
    prior_max=prior_games.date.max();current_min=current_games.date.min()
    if not (prior_games.date < SEASON_START).all() or not (prior_games.date >= pd.Timestamp('2024-11-01',tz='UTC')).all():
        raise ValueError('Prior-game season/date mismatch')
    if not (current_games.date >= SEASON_START).all():raise ValueError('Current games include prior-season dates')
    if prior_games.empty:raise ValueError('No historical prior games')
    c=pd.read_csv(candidates,dtype={'game_id':str,'home_id':str,'away_id':str})
    needed={'game_id','date','home_id','away_id','cap_uncapped','forecast_cutoff_utc'}
    if needed-set(c):raise ValueError('Missing candidate columns: '+str(needed-set(c)))
    if c.game_id.duplicated().any():raise ValueError('Duplicate candidate game IDs')
    c['date']=pd.to_datetime(c.date,utc=True,errors='coerce')
    c['cutoff']=pd.to_datetime(c.forecast_cutoff_utc,utc=True,errors='coerce')
    if c.date.isna().any() or c.cutoff.isna().any() or (c.cutoff>c.date).any():raise ValueError('Forecast cutoff not pregame')
    c=c[(c.date>=SEASON_START)&(c.date<EVAL_END)].copy()
    if c.empty:return pd.DataFrame(),{'status':'NO_EARLY_FORECASTS','reason':'V91 archive contains no Nov-Jan forecast games; no evaluation done.'}
    c=c.merge(current_games[['game_id','date','home_id','away_id','home_points','away_points','neutral_site']],on='game_id',how='inner',validate='one_to_one',suffixes=('','_game'))
    if c.empty:return pd.DataFrame(),{'status':'NO_MATCHED_EARLY_GAMES'}
    if not ((c.home_id==c.home_id_game)&(c.away_id==c.away_id_game)).all():raise ValueError('Candidate and actual teams mismatch')
    if (c.date!=c.date_game).any():raise ValueError('Candidate dates mismatch')
    if (c.cutoff>c.date).any():raise ValueError('Pregame leak')
    c['cap_uncapped']=pd.to_numeric(c.cap_uncapped,errors='coerce')
    c=c.dropna(subset=['cap_uncapped']).copy()
    old,old_counts=ridge_strength(prior_games,cap=None)
    team_set=set(old)
    deltas,roster_meta=roster_adjustments(roster)
    results=[];snapshots={}
    for r in c.sort_values(['cutoff','game_id']).itertuples(index=False):
        cutoff=r.cutoff
        if cutoff not in snapshots:
            train=current_games[current_games.date<cutoff]
            current,counts=ridge_strength(train,cap=None)
            snapshots[cutoff]=(current,counts,len(train))
        current,counts,ntrain=snapshots[cutoff]
        h,a=r.home_id,r.away_id
        # Only evaluate when both teams had prior-season ratings. Otherwise no legitimate preseason data.
        if h not in team_set or a not in team_set:continue
        home=0. if r.neutral_site else 3.
        prev=old[h]-old[a]+home
        full=r.cap_uncapped
        # Opponent-adjusted raw current ratings are the natural blend target. Do not
        # reconstruct them from a final-game score or any later season data.
        raw=current.get(h,0.)-current.get(a,0.)+home
        wh=blend_weight(counts.get(h,0));wa=blend_weight(counts.get(a,0))
        def prior_blend(shrink,with_roster=False):
            ph=shrink*old[h]+(deltas.get(h,0.) if with_roster else 0.)
            pa=shrink*old[a]+(deltas.get(a,0.) if with_roster else 0.)
            return (wh*current.get(h,0.)+(1-wh)*ph)-(wa*current.get(a,0.)+(1-wa)*pa)+home
        results.append({'game_id':r.game_id,'date':r.date,'cutoff':cutoff,'home_id':h,'away_id':a,'neutral_site':r.neutral_site,
          'actual_margin':float(r.home_points-r.away_points),'baseline_uncapped_v91':full,
          'current_ridge_without_prior':raw,'prior_only':prev,
          'blend_50pct_prior':prior_blend(.5),'blend_100pct_prior':prior_blend(1.),
          'home_games_before':counts.get(h,0),'away_games_before':counts.get(a,0),
          'training_games_before':ntrain,'roster_delta_coverage':h in deltas and a in deltas,
          'blend_roster_scenario':prior_blend(.5,True) if (h in deltas and a in deltas) else np.nan})
    out=pd.DataFrame(results)
    if out.empty:return out,{'status':'NO_MATCHED_PRIOR_TEAM_GAMES','prior_teams':len(old),'prior_games':len(prior_games)}
    models=['baseline_uncapped_v91','current_ridge_without_prior','prior_only','blend_50pct_prior','blend_100pct_prior']
    result={'status':'EARLY_SEASON_HISTORICAL_RESEARCH','season':'2025-26','evaluation_range':'2025-11-01 to 2026-01-31',
      'prior_season':'2024-25','prior_games':len(prior_games),'prior_teams':len(old),
      'matched_games':len(out),'roster':roster_meta,
      'warnings':['2025-26 has been explored; this is not a fresh untouched holdout.',
         'Prior-only vs blend comparisons are research proxies, NOT official Courtside production forecasts.',
         'The roster scenario is evaluated ONLY when both opponents have user-supplied evidence and deltas; not point-in-time verified by the workflow.',
         'Previous season game data are not prior-season preseason roster details.',
         'Different matchup coverage across models must not be interpreted as an improvement.'],
      'overall':{k:score(out.actual_margin,out[k]) for k in models},'by_month':{},'by_games_played':{}}
    for m,g in out.groupby(out.date.dt.strftime('%Y-%m')):
        result['by_month'][str(m)]={k:score(g.actual_margin,g[k]) for k in models}
    low=np.minimum(out.home_games_before,out.away_games_before)
    for title,mask in [('0-2',low<3),('3-5',(low>=3)&(low<=5)),('6-10',(low>=6)&(low<=10)),('11+',low>=11)]:
        g=out[mask]
        if not g.empty:result['by_games_played'][title]={k:score(g.actual_margin,g[k]) for k in models}
    complete=out[out.roster_delta_coverage].copy()
    if len(complete)>=30:
        result['roster_scenario']={'games':len(complete), 'prior_without_roster':score(complete.actual_margin,complete.blend_50pct_prior),
                                  'user_supplied_roster_delta':score(complete.actual_margin,complete.blend_roster_scenario)}
    else:
        result['roster_scenario']={'status':'NOT_EVALUATED','eligible_matched_games':len(complete), 'minimum_needed':30}
    return out,result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--prior-games',required=True);p.add_argument('--current-games',required=True)
    p.add_argument('--prior-venues',required=True);p.add_argument('--current-venues',required=True)
    p.add_argument('--candidates',required=True);p.add_argument('--division',choices=['mens','womens'],required=True)
    p.add_argument('--roster-evidence');p.add_argument('--out',required=True)
    a=p.parse_args()
    prior=prepare_games(a.prior_games,a.prior_venues)
    current=prepare_games(a.current_games,a.current_venues)
    df,report=run(prior,current,a.candidates,a.roster_evidence)
    report['division']=a.division
    dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
    (dest/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    if not df.empty:df.to_csv(dest/'matched_early_season_predictions.csv.gz',index=False,compression='gzip')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()

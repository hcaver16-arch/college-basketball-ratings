"""Courtside V105: strictly research-only, bounded roster sensitivity experiment.
No application/rating engine imports or mutations. Heuristics are NOT trained/validated.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

DIVISIONS=('mens-college-basketball','womens-college-basketball')

def load(path, required):
    if not path.exists():
        raise FileNotFoundError(f'Missing {path}; run V103 and V104 first')
    df=pd.read_csv(path,dtype={'team_id':'string','Team ID':'string'},low_memory=False)
    missing=set(required)-set(df.columns)
    if missing: raise ValueError(f'{path}: missing {sorted(missing)}')
    df['team_id']=df['team_id'].astype('string').str.strip()
    if df.team_id.isna().any() or df.team_id.duplicated().any():
        raise ValueError(f'{path}: invalid or duplicate team_id')
    return df

def num(df,key):
    return pd.to_numeric(df[key],errors='coerce')

def build(v103, v104, division, baseline=None):
    prior=load(v103/f'{division}_team_continuity.csv', ['team_id','returning_minutes_pct_documented','prior_roster_players','evidence_quality'])
    origins=load(v104/f'{division}_origin_summary.csv', ['team_id','team','current_players','returning_same_id','cross_school_unique_id',
                            'cross_school_with_documented_prior_stats','unknown_origin','cross_school_ambiguous_id',
                            'incoming_prior_minutes_documented','historical_boxscores_complete'])
    t=origins.merge(prior[['team_id','returning_minutes_pct_documented','prior_roster_players','evidence_quality']],on='team_id',how='left',validate='one_to_one')
    if t['prior_roster_players'].isna().any():
        raise ValueError('V103 lacks some V104 teams; re-run V103 and V104 from same archive snapshot')
    n=num(t,'current_players')
    ret=num(t,'returning_minutes_pct_documented')/100
    incoming=num(t,'incoming_prior_minutes_documented')
    unique=num(t,'cross_school_unique_id')
    documented=num(t,'cross_school_with_documented_prior_stats')
    unknown=num(t,'unknown_origin'); ambiguous=num(t,'cross_school_ambiguous_id')
    valid=(n>0)&(num(t,'prior_roster_players')>0)&ret.notna()&(ret.between(0,1))
    t['data_available']=valid
    t['returning_minutes_fraction']=ret.where(valid)
    t['origin_coverage_fraction']=((n-unknown-ambiguous)/n).where(n>0).clip(0,1)
    t['incoming_stat_coverage_fraction']=(documented/unique).where(unique>0)
    # Historical minutes are not forecasts; saturate their influence, never reward massive incoming team totals linearly.
    t['incoming_minutes_per_roster_spot']=(incoming/n).where(n>0)
    # Single-scale division-relative dimensionless measures; one roster slot ~ 15x30 = 450 minutes as a reference.
    t['incoming_experience_proxy']=(t['incoming_minutes_per_roster_spot']/450).clip(0,1)
    # Heuristic 50/50 blend of observed returning share & cross-school historical participation,
    # relative to division peers, multiplied by explicit data-coverage confidence.
    base=0.5*t['returning_minutes_fraction']+0.5*t['incoming_experience_proxy']
    typical=float(base[valid].median()) if valid.any() else 0.5
    coverage=t['origin_coverage_fraction'].fillna(0)
    historical=num(t,'historical_boxscores_complete') if False else t['historical_boxscores_complete'].astype('string').str.lower().eq('true')
    t['confidence_weight']=(coverage * (0.8+0.2*historical.astype(float))).where(valid,0).clip(0,1)
    t['roster_signal_centered']=(base-typical).where(valid)
    # Nominal +/- 2-point sensitivity cap, NOT an estimated impact; with a deliberately reduced default strength.
    t['illustrative_adjustment_points']=(2.0*t['roster_signal_centered']*t['confidence_weight']).clip(-2,2).where(valid)
    t['quality_warning']=''
    t.loc[~valid,'quality_warning']='UNAVAILABLE: no valid prior-season returning-minute evidence'
    t.loc[valid&(~historical),'quality_warning']='Historical boxscore coverage partial/unverified'
    t.loc[(valid)&(coverage<0.65),'quality_warning']=t.loc[(valid)&(coverage<0.65),'quality_warning'].apply(lambda s:(s+'; ' if s else '')+'Low roster-origin coverage')
    t.loc[t['team_id'].eq('2697'),'quality_warning']='West Florida prior D2 history absent; no roster adjustment'
    if division.startswith('womens'):
        t.loc[t['team_id'].eq('2426'),'quality_warning']='Navy: ESPN game 401823071 player box score missing; provisional'
    t['experimental_roster_index']=base.where(valid)
    t['roster_index_rank']=t['experimental_roster_index'].rank(ascending=False,method='min').astype('Int64')
    baseline_used=False
    if baseline is not None:
        b=pd.read_csv(baseline,dtype={'team_id':'string'})
        if 'division' in b: b=b[b['division'].astype(str)==division]
        if not {'team_id','baseline_rating'}.issubset(b.columns):
            raise ValueError('Optional baseline must have team_id, baseline_rating and optionally division')
        b=b[['team_id','baseline_rating']].copy();b['team_id']=b.team_id.astype('string').str.strip()
        if b.team_id.duplicated().any(): raise ValueError('Baseline has duplicate team ID')
        b['baseline_rating']=pd.to_numeric(b.baseline_rating,errors='coerce')
        t=t.merge(b,on='team_id',how='left',validate='one_to_one')
        t['experimental_rating']=t['baseline_rating']+t['illustrative_adjustment_points'].fillna(0)
        t['baseline_rank']=t['baseline_rating'].rank(ascending=False,method='min').astype('Int64')
        t['experimental_rank']=t['experimental_rating'].rank(ascending=False,method='min').astype('Int64')
        t['rank_change']=t['baseline_rank']-t['experimental_rank']
        baseline_used=True
    else:
        for c in ['baseline_rating','experimental_rating','baseline_rank','experimental_rank','rank_change']:
            t[c]=pd.NA
    return t,{'teams':len(t),'data_available':int(valid.sum()),'unavailable':int((~valid).sum()),
                'with_partial_reported_boxscores':int((valid&~historical).sum()),
                'with_low_origin_coverage':int((valid&(coverage<0.65)).sum()),
                'with_baseline_ratings':int(t['baseline_rating'].notna().sum()) if baseline_used else 0,
                'division_median_composite_index':round(typical,4),
                'baseline_used':baseline_used}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--v103',default='data/returning_production_v103')
    ap.add_argument('--v104',default='data/transfer_origin_v104')
    ap.add_argument('--out',default='data/roster_experiment_v105')
    ap.add_argument('--baseline',default=None,help='Optional research baseline CSV: team_id, baseline_rating, optional division. NEVER updates original ratings.')
    args=ap.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    baseline=Path(args.baseline) if args.baseline else None
    if baseline is not None and not baseline.is_file(): raise FileNotFoundError(baseline)
    report={'version':105,'generated_at_utc':datetime.now(timezone.utc).isoformat(),
      'status':'RESEARCH_ONLY_UNCALIBRATED_SENSITIVITY_NOT_A_PREDICTIVE_MODEL',
      'formula':'raw = .5*returning_minutes_fraction + .5*min(incoming_prior_minutes/current_roster_players/450,1); adjustment = clip(2*(raw - division_median_raw)*coverage_weight,-2,2); coverage_weight=observed_origin_fraction*(0.8+0.2*complete_own_boxscores)',
      'limitations':['No previous school-strength normalization; no role/eligibility/recruiting correction',
      'Documented minutes are historical evidence, not expected minutes or future points',
      'Transfer matching by ESPN ID is not proof of eligibility or enrollment',
      'Unknown-origin players are not assumed to have zero skill',
      'The 450-minute normalization and 2-point multiplier are illustrative, not fitted',
      'Roster index ranks are not power rankings',
      'Without an explicitly supplied baseline there are no rating or rank changes',
      'No official ratings, forecast snapshots, or application code modified'], 'divisions':{}}
    for division in DIVISIONS:
        table, stats=build(Path(args.v103),Path(args.v104),division,baseline)
        table.to_csv(out/f'{division}_experimental_roster_sensitivity.csv',index=False)
        report['divisions'][division]=stats
        print(division,stats,flush=True)
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()

#!/usr/bin/env python3
"""V118: RETROSPECTIVE, NON-VALIDATED previous-calendar-date sensitivity study.
No season-correct priors, no historical source availability guarantee, no production writes.
"""
import argparse,csv,gzip,json,math,collections,datetime
from pathlib import Path
import numpy as np
from scipy.sparse import coo_matrix, vstack, eye
from scipy.sparse.linalg import lsqr

SEASONS=('2024-25','2025-26')
DIVS=('mens-college-basketball','womens-college-basketball')
# One-factor-at-a-time comparisons against reference, without optimization.
SCENARIOS=[('reference',3.0,8.0,40.0),('hca_2',2.0,8.0,40.0),('hca_4',4.0,8.0,40.0),('ridge_4',3.0,4.0,40.0),('ridge_12',3.0,12.0,40.0),('cap_25',3.0,8.0,25.0),('cap_50',3.0,8.0,50.0)]
FIELDS=['season','division','game_id','date_et','home_id','away_id','neutral_espn','actual_home_margin','scenario','predicted_home_margin','absolute_error','winner_correct','train_games','home_train_games','away_train_games','venue_source','cutoff_rule']

def rows(path):
    op=gzip.open if str(path).endswith('.gz') else open
    with op(path,'rt',newline='',encoding='utf-8-sig') as f:yield from csv.DictReader(f)

def identifier(x):
    x=str(x or '').strip()
    return x[:-2] if x.endswith('.0') and x[:-2].isdigit() else x

def score(x):
    try:
        n=float(x)
        return n if math.isfinite(n) else None
    except (TypeError,ValueError):return None

def truth(x):
    if x is True or str(x).lower()=='true':return True
    if x is False or str(x).lower()=='false':return False
    return None

def load_archive(root,season,division):
    sex='mens' if division.startswith('mens') else 'womens'
    file=root/'data'/'historical_efficiency'/f'{season}_{sex}_paired_games.csv.gz'
    if not file.exists():return [],'archive_missing'
    games={};conflicts=set()
    for r in rows(file):
        k=identifier(r.get('game_id')); date=str(r.get('date') or '')[:10]
        try:datetime.date.fromisoformat(date)
        except ValueError:continue
        home=identifier(r.get('home_id'));away=identifier(r.get('away_id'))
        h=score(r.get('home_points'));a=score(r.get('away_points'))
        if not (k and home and away and h is not None and a is not None and home!=away):continue
        v=(date,k,home,away,h-a)
        if k in games and games[k]!=v:conflicts.add(k)
        games[k]=v
    for k in conflicts:games.pop(k,None)
    return sorted(games.values()),f'archive_ok_conflicts_dropped_{len(conflicts)}'

def load_evidence(root):
    f=root/'data'/'game_evidence_v117'/'evidence.csv'
    if not f.exists():return {},'evidence_checkpoint_missing'
    out={};bad=collections.Counter()
    for r in rows(f):
        k=(r.get('season',''),r.get('division',''),identifier(r.get('game_id')))
        n=truth(r.get('espn_neutral_site'))
        if r.get('outcome')!='ok' or n is None or truth(r.get('team_ids_match')) is not True or truth(r.get('scores_match')) is not True or truth(r.get('eastern_date_matches_archive')) is not True or truth(r.get('espn_completed')) is not True:
            bad['failed_evidence_validation']+=1;continue
        if not r.get('espn_start_utc'):bad['missing_espn_start']+=1;continue
        if k in out and (out[k]['neutral']!=n or out[k]['date']!=r.get('archive_date')):
            bad['conflicting_evidence']+=1;out.pop(k,None);continue
        out[k]={'neutral':n,'date':r.get('archive_date'),'url':r.get('espn_url','')}
    return out,dict(bad)

def fit(train,ridge,cap):
    teams=sorted({x[2] for x in train}|{x[3] for x in train})
    idx={t:i for i,t in enumerate(teams)}; n=len(train);p=len(teams)
    if not n or not p:return {},{}
    ri=[];ci=[];vv=[];target=np.zeros(n)
    counts=collections.Counter()
    for j,(_,_,home,away,margin) in enumerate(train):
        ri.extend([j,j]);ci.extend([idx[home],idx[away]]);vv.extend([1.,-1.]);target[j]=np.clip(margin,-cap,cap)
        counts[home]+=1;counts[away]+=1
    x=coo_matrix((vv,(ri,ci)),shape=(n,p)).tocsr()
    # ridge regularization: sum((home-away - margin)^2) + ridge*sum(rating^2)
    A=vstack([x,math.sqrt(ridge)*eye(p,format='csr')],format='csr')
    b=np.concatenate([target,np.zeros(p)])
    est=lsqr(A,b,atol=1e-7,btol=1e-7,iter_lim=400)[0]
    est-=np.mean(est)
    return {t:float(est[i]) for t,i in idx.items()},counts

def evaluate(root,out,max_games,min_train,min_team):
    out.mkdir(parents=True,exist_ok=True)
    evidence,ev_stats=load_evidence(root)
    total=collections.Counter();results=[];strata={}
    for season in SEASONS:
      for div in DIVS:
        key=f'{season}/{"mens" if div.startswith("mens") else "womens"}'
        archive,status=load_archive(root,season,div)
        candidates=[g for g in archive if (season,div,g[1]) in evidence and evidence[(season,div,g[1])]['date']==g[0]]
        # Favor late-season games with a usable training history; deterministic chronological sample.
        candidates=sorted(candidates,key=lambda g:(g[0],g[1]))
        selectable=candidates[-max_games:]
        info={'archive_rows':len(archive),'archive_status':status,'evidence_matched':len(candidates),'sampled_late_dates':len(selectable),'eligible_games':0,'reasons':{}}
        rejected=collections.Counter()
        for g in selectable:
            date,gid,home,away,actual=g
            # Excludes all games on cutoff date and later; never use same-day games.
            train=[x for x in archive if x[0]<date]
            if len(train)<min_train:rejected['insufficient_previous_date_games']+=1;continue
            cache={}
            for name,hca,ridge,cap in SCENARIOS:
                variant=(ridge,cap)
                if variant not in cache:cache[variant]=fit(train,ridge,cap)
            reference_counts=cache[(8.,40.)][1]
            if min(reference_counts.get(home,0),reference_counts.get(away,0))<min_team:
                rejected['team_history_below_threshold']+=1;continue
            neutral=evidence[(season,div,gid)]['neutral']
            for name,hca,ridge,cap in SCENARIOS:
                r,counts=cache[(ridge,cap)]
                # Training ignores venue: no assumption that archived home means true home.
                pred=r.get(home,0.)-r.get(away,0.)+(0 if neutral else hca)
                correct=(pred>0)==(actual>0) if pred!=0 and actual!=0 else None
                results.append({'season':season,'division':div,'game_id':gid,'date_et':date,'home_id':home,'away_id':away,'neutral_espn':str(neutral).lower(),'actual_home_margin':actual,'scenario':name,'predicted_home_margin':round(pred,5),'absolute_error':round(abs(pred-actual),5),'winner_correct':correct if correct is not None else '', 'train_games':len(train),'home_train_games':counts.get(home,0),'away_train_games':counts.get(away,0),'venue_source':'ESPN retrospective neutralSite (not independently verified)','cutoff_rule':'training games with archive date strictly before target ET date; availability NOT verified'})
            info['eligible_games']+=1
        info['reasons']=dict(rejected);strata[key]=info
        total.update(rejected)
    path=out/'predictions.csv'
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerows(results)
    groups=collections.defaultdict(list)
    for r in results:groups[(r['division'],r['scenario'])].append(r)
    stats={}
    for (d,scenario), rr in sorted(groups.items()):
        scored=[r for r in rr if r['winner_correct']!='']
        stats.setdefault(d,{})[scenario]={'games':len(rr),'margin_mae':round(sum(r['absolute_error'] for r in rr)/len(rr),4), 'winner_accuracy':round(sum(r['winner_correct'] is True for r in scored)/len(scored),4) if scored else None,'winner_scored':len(scored)}
    summary={'version':118,'status':'RETROSPECTIVE_UNVALIDATED_DATE_CUTOFF_SENSITIVITY','production_modified':False,'research_only':True,'evidence_input_status':ev_stats,'strata':strata,'rejections':dict(total),'predictions_rows':len(results),'identical_game_sets_per_scenario':True,'comparisons':stats,'scenarios':[{'name':a,'prediction_hca':b,'ridge':c,'margin_cap':d} for a,b,c,d in SCENARIOS], 'fundamental_limitations':['Historical result availability not established. Previous-date scores may still be corrected or delayed; not leakage-free','Training margins are VENUE-AGNOSTIC. HCA values vary only at prediction time, not in the rating fit. Not a complete rating_engine.py reconstruction','ESPN neutralSite is retrospective, not independently verified','No season-correct preseason priors, blending, or roster information','Evidence sample is nonrandom and late-date selection is not held-out parameter validation','Differences are descriptive; do not select or promote best settings from these comparisons']}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# Courtside V118 — previous-date retrospective sensitivity','','**RESEARCH ONLY. NOT A VERIFIED HISTORICAL FORECAST OR ACCURACY CLAIM.**','','## Data and eligibility','']
    for s,x in strata.items():lines.append(f'- {s}: {x["eligible_games"]} evaluated; {x["evidence_matched"]} evidence-matched games; {x["archive_rows"]} source games; rejects={x["reasons"]}')
    lines+=['','## Descriptive comparisons (same game sets within each division)','']
    for d,models in stats.items():
        lines += [f'### {d}','','| Scenario | Games | MAE | Winner accuracy |','|---|---:|---:|---:|']
        for nm,v in models.items():lines.append(f'| {nm} | {v["games"]} | {v["margin_mae"]} | {v["winner_accuracy"]} |')
    lines+=['','## Caveats','','This is a retrospective sensitivity analysis of simplified, venue-agnostic ridge margin fits. Only previous-archive-date scores enter each fit. Actual first-final availability and source corrections are unknown. ESPN neutralSite is provider-reported and retrospectively retrieved. No model selection, optimization, or change to production is warranted.']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    return summary

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',default='.');ap.add_argument('--output',default='data/sensitivity_v118');ap.add_argument('--max-games-per-stratum',type=int,default=16);ap.add_argument('--min-train',type=int,default=100);ap.add_argument('--min-team-games',type=int,default=2)
    a=ap.parse_args()
    if not 1<=a.max_games_per_stratum<=150:ap.error('max games must be 1..150')
    if a.min_train<1 or a.min_team_games<1:ap.error('thresholds must be positive')
    x=evaluate(Path(a.root).resolve(),Path(a.output).resolve(),a.max_games_per_stratum,a.min_train,a.min_team_games)
    print(json.dumps({'status':x['status'],'predictions_rows':x['predictions_rows'],'strata':x['strata']},indent=2))
if __name__=='__main__':main()

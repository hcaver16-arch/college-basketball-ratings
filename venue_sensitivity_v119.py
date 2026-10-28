#!/usr/bin/env python3
"""Research-only, retrospective venue-aware sensitivity. Not a historical forecast."""
import argparse,collections,csv,datetime,gzip,json,math
from pathlib import Path
import numpy as np
from scipy.sparse import coo_matrix,diags,vstack
from scipy.sparse.linalg import lsqr
SEASONS=('2024-25','2025-26')
DIVS=('mens-college-basketball','womens-college-basketball')
SCENARIOS=(('reference',3.,8.,40.),('hca_2',2.,8.,40.),('hca_4',4.,8.,40.),('ridge_4',3.,4.,40.),('ridge_12',3.,12.,40.),('cap_25',3.,8.,25.),('cap_50',3.,8.,50.))
FIELDS=('season','division','game_id','archive_date','home_id','away_id','espn_neutral','actual_home_margin','scenario','pred_home_margin','abs_error','winner_correct','train_games','home_train_games','away_train_games','cutoff')
def readcsv(path):
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt',encoding='utf-8-sig',newline='') as f:yield from csv.DictReader(f)
def tid(s):
    s=str(s or '').strip();return s[:-2] if s.endswith('.0') and s[:-2].isdigit() else s
def number(s):
    try:
        v=float(s);return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None
def boolean(s):
    if str(s).strip().lower() in ('true','1','yes'):return True
    if str(s).strip().lower() in ('false','0','no'):return False
    return None
def load_games(root,season,div):
    sex='mens' if div.startswith('mens') else 'womens'
    file=root/'data/historical_efficiency'/f'{season}_{sex}_paired_games.csv.gz'
    if not file.exists():return {},'missing_archive'
    out={};conflicts=set()
    for r in readcsv(file):
        gid=tid(r.get('game_id'));d=str(r.get('date') or '')[:10];h=tid(r.get('home_id'));a=tid(r.get('away_id'));hp=number(r.get('home_points'));ap=number(r.get('away_points'))
        try:datetime.date.fromisoformat(d)
        except ValueError:continue
        if not gid or not h or not a or h==a or hp is None or ap is None:continue
        v=(d,gid,h,a,hp-ap,hp,ap)
        if gid in out and out[gid]!=v:conflicts.add(gid)
        out[gid]=v
    for gid in conflicts:out.pop(gid,None)
    return out,f'ok_conflicting_ids_removed_{len(conflicts)}'
def load_evidence(root):
    file=root/'data/game_evidence_v117/evidence.csv';out={};conflicts=set();counts=collections.Counter()
    if not file.exists():return out,{'missing_file':str(file)}
    for r in readcsv(file):
        key=(r.get('season'),r.get('division'),tid(r.get('game_id')))
        neutral=boolean(r.get('espn_neutral_site'))
        if r.get('outcome')!='ok' or any(boolean(r.get(x)) is not True for x in ('team_ids_match','scores_match','eastern_date_matches_archive','espn_completed')) or neutral is None or not r.get('espn_start_utc'):
            counts['invalid_evidence']+=1;continue
        v=(neutral,r.get('archive_date'))
        if key in out and out[key]!=v:conflicts.add(key)
        out[key]=v
    for k in conflicts:out.pop(k,None)
    counts['conflicting_evidence_keys']=len(conflicts);counts['usable_evidence_keys']=len(out)
    return out,dict(counts)
def fit(training,hca,ridge,cap):
    teams=sorted({g[2] for g in training}|{g[3] for g in training});indexes={t:i for i,t in enumerate(teams)}
    n=len(training);p=len(teams)
    if not n:return {},collections.Counter()
    row=[];col=[];value=[];y=np.empty(n);counts=collections.Counter()
    for j,g in enumerate(training):
        _,_,home,away,margin,_,_,neutral=g
        row.extend((j,j));col.extend((indexes[home],indexes[away]));value.extend((1.,-1.))
        # This follows the live rating_engine calculation ordering:
        # clip raw result margin, THEN subtract HCA for non-neutral games.
        y[j]=np.clip(margin,-cap,cap)-(0. if neutral else hca)
        counts[home]+=1;counts[away]+=1
    x=coo_matrix((value,(row,col)),shape=(n,p)).tocsr()
    matrix=vstack([x,diags([math.sqrt(ridge)]*p,0,format='csr')],format='csr')
    ratings=lsqr(matrix,np.r_[y,np.zeros(p)],atol=1e-9,btol=1e-9,iter_lim=1500)[0]
    ratings-=ratings.mean()
    return {t:float(ratings[i]) for t,i in indexes.items()},counts
def analyze(root,out,max_games,min_train,min_team):
    out.mkdir(parents=True,exist_ok=True)
    evidence,ev_status=load_evidence(root);records=[];coverage={};rejections=collections.Counter()
    for season in SEASONS:
      for div in DIVS:
        archive,archive_status=load_games(root,season,div)
        labeled=[]
        for gid,g in archive.items():
            ev=evidence.get((season,div,gid))
            if ev and ev[1]==g[0]:labeled.append(g+(ev[0],))
        labeled.sort(key=lambda g:(g[0],g[1]))
        targets=labeled[-max_games:]
        key=f'{season}/{"mens" if div.startswith("mens") else "womens"}'
        info={'archive_games':len(archive),'archive_status':archive_status,'venue_labeled_games':len(labeled),'selected_targets':len(targets),'scored_targets':0,'excluded':{}}
        fail=collections.Counter()
        for target in targets:
            day,gid,home,away,actual,_,_,neutral=target
            train=[g for g in labeled if g[0]<day]
            if len(train)<min_train:fail['too_few_prior_venue_labeled_games']+=1;continue
            counts=collections.Counter(t for g in train for t in (g[2],g[3]))
            if min(counts[home],counts[away])<min_team:fail['team_has_too_few_prior_games']+=1;continue
            for name,hca,ridge,cap in SCENARIOS:
                ratings,tc=fit(train,hca,ridge,cap)
                predicted=ratings.get(home,0.)-ratings.get(away,0.)+(0. if neutral else hca)
                correct=None if predicted==0 or actual==0 else int((predicted>0)==(actual>0))
                records.append(dict(season=season,division=div,game_id=gid,archive_date=day,home_id=home,away_id=away,espn_neutral=str(neutral).lower(),actual_home_margin=actual,scenario=name,pred_home_margin=round(predicted,6),abs_error=round(abs(predicted-actual),6),winner_correct='' if correct is None else correct,train_games=len(train),home_train_games=tc[home],away_train_games=tc[away],cutoff='archive dates strictly before target date; availability unverified'))
            info['scored_targets']+=1
        info['excluded']=dict(fail);rejections.update(fail);coverage[key]=info
    with (out/'predictions.csv').open('w',encoding='utf-8',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=FIELDS);wr.writeheader();wr.writerows(records)
    groups=collections.defaultdict(list)
    for r in records:groups[(r['division'],r['scenario'])].append(r)
    stats={}
    for (div,scenario),group in sorted(groups.items()):
        non_ties=[r for r in group if r['winner_correct']!='']
        stats.setdefault(div,{})[scenario]={'games':len(group),'margin_mae':round(sum(r['abs_error'] for r in group)/len(group),4),'winner_accuracy':round(sum(int(r['winner_correct']) for r in non_ties)/len(non_ties),4) if non_ties else None,'winner_scored':len(non_ties)}
    summary={'version':119,'status':'RETROSPECTIVE_UNVERIFIED_VENUE_AWARE_SENSITIVITY','production_modified':False,'model_variant_promoted':False,'source_engine_reference':'rating_engine.py calculate_power: clipped home margin minus fixed venue HCA, ridge least squares, centered ratings','scope':'on-court component only; training restricted to ESPN evidence checkpoint games','evidence':ev_status,'coverage':coverage,'rejections':dict(rejections),'prediction_rows':len(records),'all_scenarios_same_game_set':True,'scenarios':[dict(name=n,hca=h,ridge=r,margin_cap=c) for n,h,r,c in SCENARIOS],'results':stats,'limitations':['NOT historical forecasts or leakage-free backtests: actual historical first-final availability is unknown','ESPN venue labels obtained retrospectively are not independently verified','Only ESPN venue-labeled checkpoint games used to fit; this differs from full production history','Preseason blend, priors, roster effects, D1 filters, evolving schedules and current production rounding excluded','Selections are late games from a nonrandom 200-per-stratum sample; not out-of-sample tuning evidence','Venue-aware HCA is subtracted from clipped margins during TRAINING and added at prediction as in rating_engine.py','No hyperparameter selection or production modification']}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# Courtside V119 — venue-aware historical sensitivity','','**RESEARCH ONLY — not verified historical forecasts or proof of accuracy.**','','## Eligibility and coverage','']
    for k,v in coverage.items():lines.append(f'- {k}: {v["scored_targets"]}/{v["selected_targets"]} targets; {v["venue_labeled_games"]} labeled archived games; excluded={v["excluded"]}')
    lines+=['','## Same-game descriptive results','']
    for div,models in stats.items():
        lines.extend((f'### {div}','','| Scenario | Games | MAE | Winner accuracy |','|---|---:|---:|---:|'))
        for n,v in models.items():lines.append(f'| {n} | {v["games"]} | {v["margin_mae"]} | {v["winner_accuracy"]} |')
        lines.append('')
    lines+=['## Interpretation','','Compared with V118, home-court adjustment is used for both training and prediction. The reference uses the on-court math of the live rating engine, but not its full-season inputs, priors or blending. Differences are descriptive only. Historical first-final timestamps and independent venue verification remain missing. Do not change the live model from these results.']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    return summary
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',default='.')
    parser.add_argument('--output',default='data/sensitivity_v119')
    parser.add_argument('--max-games-per-stratum',type=int,default=60)
    parser.add_argument('--min-train',type=int,default=60)
    parser.add_argument('--min-team-games',type=int,default=1)
    args=parser.parse_args()
    if not 1<=args.max_games_per_stratum<=200 or args.min_train<1 or args.min_team_games<1:parser.error('Invalid sample or minimum threshold')
    s=analyze(Path(args.root).resolve(),Path(args.output).resolve(),args.max_games_per_stratum,args.min_train,args.min_team_games)
    print(json.dumps({'status':s['status'],'prediction_rows':s['prediction_rows'],'coverage':s['coverage']},indent=2))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Courtside V120: research-only ESPN coverage expansion and paired uncertainty.
Retrospective, not historical forecasts. Does not alter production files.
"""
import argparse,csv,gzip,hashlib,json,math,os,re,time,collections,random
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
from zoneinfo import ZoneInfo
import numpy as np
from scipy.sparse import coo_matrix,diags,vstack
from scipy.sparse.linalg import lsqr
SEASONS=('2024-25','2025-26')
DIVISIONS=('mens-college-basketball','womens-college-basketball')
SCENARIOS=(('reference',3.,8.,40.),('hca_2',2.,8.,40.),('hca_4',4.,8.,40.),('ridge_4',3.,4.,40.),('ridge_12',3.,12.,40.),('cap_25',3.,8.,25.),('cap_50',3.,8.,50.))
COLUMNS=['season','division','game_id','archive_date','archive_home_id','archive_away_id','archive_home_points','archive_away_points','source_path','espn_url','retrieved_utc','response_sha256','outcome','http_status','espn_start_utc','espn_date_eastern','eastern_date_matches_archive','espn_home_id','espn_away_id','espn_home_points','espn_away_points','team_ids_match','scores_match','espn_neutral_site','archived_venue_text','archived_neutral_label','venue_label_comparison','espn_completed','date_disagreement','duplicate_conflict','final_available_utc','independently_verified_venue','eligible_strict_replay','warnings']
PRED_COLUMNS=['season','division','game_id','archive_date','home_id','away_id','neutral','actual_margin','scenario','predicted_margin','abs_error','winner_correct','training_game_count','home_prior_count','away_prior_count']


def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def normid(x):
    s=str(x or '').strip()
    return str(int(float(s))) if re.fullmatch(r'\d+(?:\.0+)?',s) else s

def num(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError): return None

def timestamp(s):
    try:
        d=datetime.fromisoformat(str(s).replace('Z','+00:00'))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except (ValueError,TypeError): return None

def csvrows(path):
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt',encoding='utf-8-sig',newline='') as f:
        yield from csv.DictReader(f)

def archive_venues(root):
    result={}; conflicts=Counter()
    for div in DIVISIONS:
        path=root/'data'/'ratings'/div/'history_2025-26.csv.gz'
        if not path.exists():continue
        for r in csvrows(path):
            gid=normid(r.get('Game ID')); venue=str(r.get('Venue') or '').strip()
            if not gid or not venue:continue
            key=(div,gid)
            if key in result and result[key]!=venue: conflicts[key]+=1
            else:result[key]=venue
    return result,set(conflicts)

def venue_label(v):
    s=str(v or '').strip().lower()
    if s in ('neutral','neutral site','neutral-site','n'):return 'neutral'
    if s in ('home','home site','home-site','h'):return 'non_neutral'
    return 'unknown'

def retrieve(url,timeout,retries,pause):
    for attempt in range(retries+1):
        try:
            req=Request(url,headers={'User-Agent':'CourtsideHistoricalResearch/117','Accept':'application/json'})
            with urlopen(req,timeout=timeout) as res:
                b=res.read(5_000_001)
                if len(b)>5_000_000:return {},'oversize','',res.status
                return json.loads(b.decode('utf-8')),'ok',hashlib.sha256(b).hexdigest(),res.status
        except HTTPError as e:
            if e.code in (429,500,502,503,504) and attempt<retries:
                time.sleep(pause*(attempt+1));continue
            return {},f'http_{e.code}','',e.code
        except (URLError, TimeoutError, OSError, ValueError) as e:
            if attempt<retries:time.sleep(pause*(attempt+1));continue
            return {},f'fetch_{type(e).__name__}','',''
    return {},'unknown','',''

def interpret(data,item,archived_venues,venue_conflicts):
    hdr=data.get('header') or {}
    comps=hdr.get('competitions') or []
    c=comps[0] if comps else {}
    sides={}
    for p in c.get('competitors') or []:
        loc=p.get('homeAway'); team=p.get('team') or {}
        if loc in ('home','away'):sides[loc]=(normid(team.get('id')),num(p.get('score')))
    home=sides.get('home',('','')); away=sides.get('away',('',''))
    ds=c.get('date') or hdr.get('date'); utc=timestamp(ds)
    et=utc.astimezone(ZoneInfo('America/New_York')).date().isoformat() if utc else ''
    neutral=c.get('neutralSite')
    if type(neutral)!=bool:neutral=''
    status=(c.get('status') or hdr.get('status') or {}).get('type') or {}
    completed=status.get('completed') is True
    key=(item['division'],item['game_id'])
    txt=archived_venues.get(key,''); label=venue_label(txt)
    if key in venue_conflicts:comparison='archive_venue_internal_conflict'
    elif neutral=='' or not txt:comparison='not_comparable'
    elif label=='unknown':comparison='archive_venue_label_ambiguous'
    elif (label=='neutral')==neutral:comparison='labels_agree_NOT_independent_verification'
    else:comparison='labels_disagree'
    id_match=home[0]==item['archive_home_id'] and away[0]==item['archive_away_id']
    scores_match=home[1]==item['archive_home_points'] and away[1]==item['archive_away_points']
    warnings=[]
    if not id_match:warnings.append('team_ids_disagree')
    if not scores_match:warnings.append('scores_disagree')
    if utc and et!=item['archive_date']:warnings.append('eastern_date_differs')
    if comparison=='labels_disagree':warnings.append('venue_labels_disagree')
    if not completed:warnings.append('not_marked_completed')
    return {'espn_start_utc':utc.isoformat().replace('+00:00','Z') if utc else '', 'espn_date_eastern':et,
            'eastern_date_matches_archive':et==item['archive_date'] if et else '',
            'espn_home_id':home[0],'espn_away_id':away[0],'espn_home_points':home[1],'espn_away_points':away[1],
            'team_ids_match':id_match,'scores_match':scores_match,'espn_neutral_site':neutral,
            'archived_venue_text':txt,'archived_neutral_label':label,'venue_label_comparison':comparison,
            'espn_completed':completed,'date_disagreement':bool(et and et!=item['archive_date']),
            'duplicate_conflict':key in venue_conflicts,'final_available_utc':'','independently_verified_venue':False,
            'eligible_strict_replay':False,'warnings':';'.join(warnings)}

def load_checkpoint(path):
    found={}
    if not path.exists():return found
    for r in csvrows(path):
        if r.get('season') and r.get('division') and r.get('game_id'):
            found[(r['season'],r['division'],normid(r['game_id']))]=r
    return found

def write_csv(path,rows):
    tmp=path.with_suffix('.tmp')
    with tmp.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=COLUMNS,extrasaction='ignore');w.writeheader();w.writerows(rows)
    os.replace(tmp,path)

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
        try:__import__("datetime").date.fromisoformat(d)
        except ValueError:continue
        if not gid or not h or not a or h==a or hp is None or ap is None:continue
        v=(d,gid,h,a,hp-ap,hp,ap)
        if gid in out and out[gid]!=v:conflicts.add(gid)
        out[gid]=v
    for gid in conflicts:out.pop(gid,None)
    return out,f'ok_conflicting_ids_removed_{len(conflicts)}'

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


def assemble_targets(root, per_stratum, old):
    """Preserve prior checkpoint and add deterministic season-spread archive matches."""
    samples=[]; stats={}
    for season in SEASONS:
      for division in DIVISIONS:
        label='mens' if division.startswith('mens') else 'womens'
        archived,status=load_games(root,season,division)
        ordered=sorted(archived.values(),key=lambda g:(g[0],g[1]))
        existing={key[2] for key in old if key[0]==season and key[1]==division and key[2] in archived}
        room=max(0,per_stratum-len(existing))
        remaining=[g for g in ordered if g[1] not in existing]
        if room>=len(remaining):addition=remaining
        elif room==1:addition=[remaining[len(remaining)//2]]
        elif room:
            addition=[remaining[(i*(len(remaining)-1))//(room-1)] for i in range(room)]
        else:addition=[]
        ids=existing|{g[1] for g in addition}
        for g in ordered:
            if g[1] in ids:
                date,gid,h,a,margin,hp,ap=g
                samples.append(dict(season=season,division=division,game_id=gid,archive_date=date,archive_home_id=h,archive_away_id=a,archive_home_points=hp,archive_away_points=ap,source_path=f'data/historical_efficiency/{season}_{label}_paired_games.csv.gz'))
        stats[f'{season}/{label}']={'archive_games':len(archived),'archive_status':status,'retained_checkpoint':len(existing),'target':len(ids),'new_to_checkpoint':len(ids-existing)}
    return samples,stats

def load_verified_evidence(root,checkpoint):
    games={}; conflicts=set(); problems=Counter()
    for row in checkpoint.values():
        key=(row.get('season'),row.get('division'),tid(row.get('game_id')))
        neutral=boolean(row.get('espn_neutral_site'))
        if row.get('outcome')!='ok' or neutral is None or any(boolean(row.get(k)) is not True for k in ('team_ids_match','scores_match','espn_completed','eastern_date_matches_archive')) or not row.get('espn_start_utc'):
            problems['missing_or_conflicting_provider_data']+=1;continue
        val=(neutral,row.get('archive_date'))
        if key in games and games[key]!=val:conflicts.add(key)
        games[key]=val
    for k in conflicts:games.pop(k,None)
    return games,dict(problems)

def paired_bootstrap(rows, scenario, reps=1000):
    paired=defaultdict(dict)
    for r in rows:
        paired[(r['season'],r['division'],r['game_id'])][r['scenario']]=r
    diffs=[]; wins=[]
    for pair in paired.values():
        if 'reference' in pair and scenario in pair:
            a=pair[scenario];b=pair['reference']
            diffs.append(float(a['abs_error'])-float(b['abs_error']))
            if a['winner_correct']!='' and b['winner_correct']!='':wins.append(int(a['winner_correct'])-int(b['winner_correct']))
    if not diffs:return {'paired_games':0,'mae_difference_vs_reference':None,'mae_diff_bootstrap_95pct':None,'win_accuracy_diff_vs_reference':None}
    arr=np.array(diffs,dtype=float)
    # Deterministic, descriptive percentile interval, not proof of statistical significance.
    rng=np.random.default_rng(120)
    ix=rng.integers(0,len(arr),size=(reps,len(arr)))
    draws=arr[ix].mean(axis=1)
    return {'paired_games':len(diffs),'mae_difference_vs_reference':round(float(arr.mean()),4),'mae_diff_bootstrap_95pct':[round(float(x),4) for x in np.percentile(draws,[2.5,97.5])],'win_accuracy_diff_vs_reference':round(float(np.mean(wins)),4) if wins else None,'mean_sign_note':'negative MAE difference favors scenario'}

def evaluate(root,checkpoint,output,max_targets,min_train,min_team):
    evidence,evidence_problems=load_verified_evidence(root,checkpoint)
    preds=[]; coverage={}; summaries={}; pair_stats={}
    for season in SEASONS:
      for div in DIVISIONS:
        label='mens' if div.startswith('mens') else 'womens'
        archive,st=load_games(root,season,div)
        labeled=[g+(evidence[(season,div,g[1])][0],) for g in archive.values() if (season,div,g[1]) in evidence and evidence[(season,div,g[1])][1]==g[0]]
        labeled.sort(key=lambda x:(x[0],x[1]))
        targets=labeled[-max_targets:]; failures=Counter(); scored=0
        # Date-keyed fitted scenario cache: all games on one day share earlier training data.
        fit_cache={};last_day=None
        for target in targets:
            day,gid,home,away,margin,_,_,neutral=target
            if day!=last_day:
                training=[g for g in labeled if g[0]<day]
                counts=Counter(t for g in training for t in (g[2],g[3]))
                fit_cache={};last_day=day
            if len(training)<min_train:
                failures['too_few_previous_venue_labeled_games']+=1;continue
            if min(counts[home],counts[away])<min_team:
                failures['team_missing_prior_venue_labeled_games']+=1;continue
            for name,hca,ridge,cap in SCENARIOS:
                if name not in fit_cache:fit_cache[name]=fit(training,hca,ridge,cap)[0]
                ratings=fit_cache[name]
                pred=ratings.get(home,0.)-ratings.get(away,0.)+(0 if neutral else hca)
                correct='' if pred==0 or margin==0 else int((pred>0)==(margin>0))
                preds.append({'season':season,'division':div,'game_id':gid,'archive_date':day,'home_id':home,'away_id':away,'neutral':str(neutral).lower(),'actual_margin':margin,'scenario':name,'predicted_margin':round(pred,6),'abs_error':round(abs(pred-margin),6),'winner_correct':correct,'training_game_count':len(training),'home_prior_count':counts[home],'away_prior_count':counts[away]})
            scored+=1
        coverage[f'{season}/{label}']={'archive_games':len(archive),'venue_labeled_games':len(labeled),'selected_targets':len(targets),'scored_targets':scored,'excluded':dict(failures)}
    output.mkdir(parents=True,exist_ok=True)
    with (output/'predictions.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=PRED_COLUMNS);writer.writeheader();writer.writerows(preds)
    for div in DIVISIONS:
        divrows=[r for r in preds if r['division']==div];res={}
        for name,*_ in SCENARIOS:
            rr=[r for r in divrows if r['scenario']==name];wr=[int(r['winner_correct']) for r in rr if r['winner_correct']!='']
            res[name]={'games':len(rr),'margin_mae':round(float(np.mean([r['abs_error'] for r in rr])),4) if rr else None,'winner_accuracy':round(float(np.mean(wr)),4) if wr else None,'paired_comparison':paired_bootstrap(divrows,name) if rr and name!='reference' else None}
        summaries[div]=res
        pair_stats[div]={name:res[name]['paired_comparison'] for name,*_ in SCENARIOS if name!='reference'}
    return {'coverage':coverage,'results':summaries,'prediction_rows':len(preds),'evidence_issues':evidence_problems,'scored_games':len(preds)//len(SCENARIOS)}


# V121: research-only cross-season replication. V120 was inspected in both seasons;
# 2025-26 is NOT an untouched holdout. No downloads or checkpoint modifications.
def date_cluster_interval(pairs, rounds=2000):
    bydate=defaultdict(list)
    for r in pairs:
        bydate[r['archive_date']].append(r['difference'])
    if not bydate:return None
    dates=sorted(bydate);rng=np.random.default_rng(121);draw=[]
    for _ in range(rounds):
        chosen=rng.integers(0,len(dates),len(dates))
        samples=[x for i in chosen for x in bydate[dates[i]]]
        draw.append(sum(samples)/len(samples))
    return [round(float(x),4) for x in np.quantile(draw,[.025,.975])]

def group_summary(rows):
    results={}
    for name,*_ in SCENARIOS:
        sub=[r for r in rows if r['scenario']==name]
        if not sub:results[name]={'games':0,'mae':None,'winner_accuracy':None,'mae_difference':None,'clustered_date_95pct':None};continue
        wins=[r['winner_correct'] for r in sub if r['winner_correct']!='']
        refs={(r['season'],r['division'],r['game_id']):r for r in rows if r['scenario']=='reference'}
        paired=[{'archive_date':r['archive_date'],'difference':r['abs_error']-refs[(r['season'],r['division'],r['game_id'])]['abs_error']} for r in sub if (r['season'],r['division'],r['game_id']) in refs]
        results[name]={'games':len(sub),'mae':round(float(np.mean([r['abs_error'] for r in sub])),4),
                       'winner_accuracy':round(float(np.mean(wins)),4) if wins else None,
                       'mae_difference':round(float(np.mean([x['difference'] for x in paired])),4) if name!='reference' else None,
                       'clustered_date_95pct':date_cluster_interval(paired) if name!='reference' else None,
                       'unique_evaluation_dates':len({r['archive_date'] for r in sub})}
    return results

def run_v121(args):
    root=Path(args.root).resolve();output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True)
    cp=root/'data/game_evidence_v117/evidence.csv'
    evidence,problems=load_verified_evidence(root,load_checkpoint(cp))
    predictions=[];coverage={}; warnings=[]
    if not cp.exists():warnings.append('missing_v117_evidence_checkpoint')
    for season in SEASONS:
      for div in DIVISIONS:
        label='mens' if div.startswith('mens') else 'womens';key=f'{season}/{label}'
        archive,status=load_games(root,season,div)
        labeled=[g+(evidence[(season,div,g[1])][0],) for g in archive.values()
                 if (season,div,g[1]) in evidence and evidence[(season,div,g[1])][1]==g[0]]
        labeled.sort(key=lambda g:(g[0],g[1]))
        targets=labeled[-args.max_targets:];exclusions=Counter();scored=0;lastday=None;cache={}
        for target in targets:
            day,gid,home,away,margin,_,_,neutral=target
            if lastday!=day:
                training=[g for g in labeled if g[0]<day]
                counts=Counter(t for g in training for t in (g[2],g[3]))
                cache={};lastday=day
            if len(training)<args.min_train:
                exclusions['too_few_prior_labeled_games']+=1;continue
            if min(counts[home],counts[away])<args.min_team_games:
                exclusions['team_missing_prior_labeled_games']+=1;continue
            for name,hca,ridge,cap in SCENARIOS:
                if name not in cache:cache[name]=fit(training,hca,ridge,cap)[0]
                ratings=cache[name]
                prediction=ratings[home]-ratings[away]+(0 if neutral else hca)
                correct='' if prediction==0 or margin==0 else int((prediction>0)==(margin>0))
                predictions.append({'season':season,'division':div,'game_id':gid,'archive_date':day,
                    'home_id':home,'away_id':away,'neutral':str(neutral).lower(),
                    'actual_margin':margin,'scenario':name,'predicted_margin':round(prediction,6),
                    'abs_error':round(abs(prediction-margin),6),'winner_correct':correct,
                    'training_game_count':len(training),'home_prior_count':counts[home],
                    'away_prior_count':counts[away]})
            scored+=1
        coverage[key]={'source_status':status,'archive_games':len(archive),'venue_labeled_games':len(labeled),
                       'selected_targets':len(targets),'scored_targets':scored,'excluded':dict(exclusions)}
    with (output/'predictions.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=PRED_COLUMNS);w.writeheader();w.writerows(predictions)
    by_season={};by_division={};by_venue={}
    for season in SEASONS:
        by_season[season]={div:group_summary([r for r in predictions if r['season']==season and r['division']==div]) for div in DIVISIONS}
    for div in DIVISIONS:
        by_division[div]=group_summary([r for r in predictions if r['division']==div])
        by_venue[div]={v:group_summary([r for r in predictions if r['division']==div and r['neutral']==v]) for v in ('true','false')}
    # Previous season is retrospective exploratory; next season was already seen in V118-V120.
    headline={}
    for div in DIVISIONS:
        a=by_season['2024-25'][div]['ridge_4']; b=by_season['2025-26'][div]['ridge_4']
        headline[div]={'ridge4_2024_25_delta_mae':a['mae_difference'],'ridge4_2025_26_delta_mae':b['mae_difference'],
                       'same_sign':(a['mae_difference']*b['mae_difference']>0) if a['mae_difference'] is not None and b['mae_difference'] is not None else None}
    summary={'version':121,'status':'RESEARCH_ONLY_CROSS_SEASON_REPLICATION_NOT_UNTOUCHED_HOLDOUT',
        'production_modified':False,'evidence_modified':False,'source_checkpoint':str(cp.relative_to(root)) if cp.is_relative_to(root) else str(cp),
        'scored_games':len(predictions)//len(SCENARIOS),'coverage':coverage,'evidence_issues':problems,
        'by_season':by_season,'by_division':by_division,'by_venue':by_venue,'ridge4_replication':headline,
        'warnings':warnings,'limitations':[
          '2025-26 was previously evaluated in V118-V120 and cannot be claimed as a genuinely untouched holdout.',
          'Only previous-archive-date results in venue-labeled subset; historical first-final timestamps unavailable.',
          'Nonrandom season-spread ESPN subset and late-date targets; not a representative season-level accuracy claim.',
          'ESPN venue flags retrospectively fetched, not independently verified.',
          'Date-cluster bootstrap is descriptive, does not account for team/opponent correlations or previous model comparisons.',
          'On-court portion only; production preseason priors, blends, rosters, D1 filtering not reproduced.',
          'Results exploratory: no model hyperparameter selection or live model promotion.']}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# Courtside V121 — cross-season stability and temporal replication','','**Research-only: 2025–26 is NOT an untouched holdout.**','',
           f'Evaluated **{summary["scored_games"]}** distinct games. No ESPN retrievals; no production or checkpoint writes.','',
           '## Coverage','']
    for k,v in coverage.items():lines.append(f'- {k}: {v["scored_targets"]} / {v["selected_targets"]} targets scored; {v["venue_labeled_games"]} venue-labeled; exclusions {v["excluded"]}')
    for season in SEASONS:
      lines+=['',f'## {season}: same-game sensitivity','',
              '| Division | Scenario | Games | MAE | Winner accuracy | Paired ΔMAE | Date-cluster 95% interval |',
              '|---|---|---:|---:|---:|---:|---|']
      for div in DIVISIONS:
        for name,*_ in SCENARIOS:
            r=by_season[season][div][name];lines.append(f'| {div} | {name} | {r["games"]} | {r["mae"]} | {r["winner_accuracy"]} | {r["mae_difference"]} | {r["clustered_date_95pct"]} |')
    lines+=['','## Ridge-4 cross-season replication','',
            '| Division | 2024–25 ΔMAE | 2025–26 ΔMAE | Same direction? |',
            '|---|---:|---:|---|']
    for div,h in headline.items():lines.append(f'| {div} | {h["ridge4_2024_25_delta_mae"]} | {h["ridge4_2025_26_delta_mae"]} | {h["same_sign"]} |')
    lines+=['','## Limitations','']+['- '+l for l in summary['limitations']]
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    return summary

def main():
    p=argparse.ArgumentParser(description='Courtside V121 read-only historical cross-season replication')
    p.add_argument('--root',default='.')
    p.add_argument('--output',default='data/research_v121')
    p.add_argument('--max-targets',type=int,default=240)
    p.add_argument('--min-train',type=int,default=60)
    p.add_argument('--min-team-games',type=int,default=1)
    args=p.parse_args()
    if not 1<=args.max_targets<=600 or args.min_train<1 or args.min_team_games<1:p.error('Invalid bounds')
    result=run_v121(args)
    print(json.dumps({'scored_games':result['scored_games'],'coverage':result['coverage'],'ridge4_replication':result['ridge4_replication']},indent=2))
if __name__=='__main__':main()

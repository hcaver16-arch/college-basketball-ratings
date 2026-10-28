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

def run_v120(args):
    root=Path(args.root).resolve();output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True)
    checkpoint_dir=root/'data/game_evidence_v117'; checkpoint_path=checkpoint_dir/'evidence.csv'
    checkpoint=load_checkpoint(checkpoint_path)
    targets,stats=assemble_targets(root,args.per_stratum,checkpoint)
    archived_venues,venue_conflicts=archive_venues(root)
    pending=[item for item in targets if (item['season'],item['division'],item['game_id']) not in checkpoint or (args.retry_failed and checkpoint[(item['season'],item['division'],item['game_id'])].get('outcome')!='ok')]
    pending=pending[:args.max_new]; outcomes=Counter()
    # Fail before expensive retrieval if checkpoint cannot be saved.
    checkpoint_dir.mkdir(parents=True,exist_ok=True)
    for idx,item in enumerate(pending):
        url=f'https://site.api.espn.com/apis/site/v2/sports/basketball/{item["division"]}/summary?event={item["game_id"]}'
        rec={k:'' for k in COLUMNS};rec.update(item);rec['espn_url']=url;rec['retrieved_utc']=now()
        data,status,sha,code=retrieve(url,args.timeout,args.retries,args.pause)
        rec.update(outcome=status,response_sha256=sha,http_status=code,final_available_utc='',independently_verified_venue=False,eligible_strict_replay=False)
        if status=='ok':rec.update(interpret(data,item,archived_venues,venue_conflicts))
        else:rec['warnings']='provider_retrieval_failed'
        checkpoint[(item['season'],item['division'],item['game_id'])]=rec
        outcomes[status]+=1
        write_csv(checkpoint_path,[checkpoint[k] for k in sorted(checkpoint)])
        if args.pause and idx<len(pending)-1:time.sleep(args.pause)
    evaluation=evaluate(root,checkpoint,output,args.max_targets,args.min_train,args.min_team_games)
    target_keys={(r['season'],r['division'],r['game_id']) for r in targets}
    present=len(target_keys & set(checkpoint)); valid=Counter(r.get('outcome','') for k,r in checkpoint.items() if k in target_keys)
    summary={'version':120,'status':'RESEARCH_ONLY_EXPANDED_VENUE_AWARE_SENSITIVITY','production_modified':False,'model_promoted':False,'target_game_count':len(targets),'target_present':present,'target_missing':len(targets)-present,'new_espn_requests':len(pending),'new_request_outcomes':dict(outcomes),'target_outcomes':dict(valid),'source_stats':stats,**evaluation,'no_historical_final_availability_verified':True,'no_independent_venue_verification':True,'strict_replay_eligible':0,'limitations':['Retrospective research sample; NOT validated or leakage-free historical predictions.','First-final result availability timestamps unavailable. Prior-date cutoff is only an approximation.','Retrospectively retrieved ESPN neutral labels are not independently verified.','Nonrandom checkpoint and target sampling, small samples and repeated comparisons.','Bootstrap intervals resample games independently; shared opponents/date correlations are not modeled.','Only on-court least squares; no historically available preseason priors, blending, roster adjustments or D1 filters.','Never select or deploy live model hyperparameters from this experiment.']}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# Courtside V120 — coverage expansion and venue-aware paired comparisons','','**RESEARCH ONLY; retrospective sensitivity, NOT a valid historical forecast backtest.**','',f'ESPN research target: **{len(targets)}**; evidence present: **{present}**; remaining: **{len(targets)-present}**; new requests: **{len(pending)}**.','',f'New retrieval outcomes: `{dict(outcomes)}`','', '## Scored coverage','']
    for k,v in evaluation['coverage'].items():lines.append(f'- {k}: {v["scored_targets"]} scored / {v["selected_targets"]} targets; {v["venue_labeled_games"]} labeled training candidates; exclusions: {v["excluded"]}')
    lines+=['','## Same-game comparisons; 95% descriptive bootstrap intervals','','Negative paired MAE difference favors a scenario over reference. Intervals are exploratory and not valid for model promotion.','']
    for div,res in evaluation['results'].items():
        lines += [f'### {div}','','| Scenario | Games | MAE | Winner accuracy | Paired MAE difference vs reference | 95% bootstrap interval |','|---|---:|---:|---:|---:|---|']
        for name,v in res.items():
            p=v['paired_comparison'];ci=str(p['mae_diff_bootstrap_95pct']) if p else '—';diff=p['mae_difference_vs_reference'] if p else '—'
            lines.append(f'| {name} | {v["games"]} | {v["margin_mae"]} | {v["winner_accuracy"]} | {diff} | {ci} |')
        lines.append('')
    lines+=['## Limitations','']+['- '+s for s in summary['limitations']]
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    return summary

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default='.')
    p.add_argument('--output',default='data/research_v120')
    p.add_argument('--per-stratum',type=int,default=600)
    p.add_argument('--max-new',type=int,default=200)
    p.add_argument('--max-targets',type=int,default=120)
    p.add_argument('--min-train',type=int,default=60)
    p.add_argument('--min-team-games',type=int,default=1)
    p.add_argument('--timeout',type=float,default=18)
    p.add_argument('--retries',type=int,default=2)
    p.add_argument('--pause',type=float,default=0.08)
    p.add_argument('--retry-failed',action='store_true')
    a=p.parse_args()
    if not 1<=a.per_stratum<=2000 or not 0<=a.max_new<=300 or not 1<=a.max_targets<=500 or a.min_train<1 or a.min_team_games<1 or a.timeout<=0 or a.pause<0 or not 0<=a.retries<=5:p.error('Invalid bounds')
    s=run_v120(a)
    print(json.dumps({'new_requests':s['new_espn_requests'],'remaining':s['target_missing'],'scored_games':s['scored_games'],'coverage':s['coverage']},indent=2))
if __name__=='__main__':main()

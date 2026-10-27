#!/usr/bin/env python3
"""Courtside V114: bounded, research-only chronological on-court rating replay.

Strict mode requires timezone-aware starts, completion and observation timestamps,
and verified venues. It never treats an outcome file's historical date as evidence
that the outcome was available then. No live rating_engine imports/edits.
"""
import argparse, csv, gzip, hashlib, json, re
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np

START=('game_start_utc','start_utc','start_time_utc','scheduled_start_utc','date_utc')
FINAL=('final_available_utc','result_available_utc','result_observed_utc','completed_at_utc','final_timestamp_utc')
VENUE=('neutral_site','neutral','is_neutral')
VERIFIED=('neutral_verified','venue_verified','verified_venue')
HOME=('home_id','home_team_id'); AWAY=('away_id','away_team_id')
HP=('home_points','home_score'); AP=('away_points','away_score')
GAME=('game_id','espn_game_id'); DIV=('division','league')

def choose(row, fields):
    norm={re.sub(r'[^a-z0-9]','',k.lower()):v for k,v in row.items() if k}
    for col in fields:
        v=norm.get(re.sub(r'[^a-z0-9]','',col.lower()))
        if v is not None and str(v).strip():return str(v).strip()
    return ''

def utc(s):
    if not s or not re.search(r'(Z|[+-]\d\d:?\d\d)$',s, re.I):return None
    try:
        dt=datetime.fromisoformat(s.replace('Z','+00:00'))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except ValueError:return None

def truth(s):
    s=str(s).strip().lower()
    return True if s in ('1','true','yes','y') else False if s in ('0','false','no','n') else None

def num(s):
    try:
        v=float(s)
        return v if np.isfinite(v) and 0<=v<=250 else None
    except (TypeError,ValueError):return None

def discover(root):
    paths=[]
    for base in ('data','research','archive'):
        d=root/base
        if not d.exists():continue
        for p in d.rglob('*'):
            if p.is_file() and (p.name.endswith('.csv') or p.name.endswith('.csv.gz')) and any(x in str(p).lower() for x in ('game','histor','result','venue','schedule')):
                if not any(x in str(p).lower() for x in ('prospective','walkforward_audit_v113','replay_v114')): paths.append(p)
    return sorted(paths,key=lambda p:str(p))[:300]

def read_csv(path, limit=250000):
    op=gzip.open if str(path).endswith('.gz') else open
    with op(path,'rt',encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f)
        for i,row in enumerate(r):
            if i>=limit:break
            yield row

def normalize(row, source, reasons):
    gid=choose(row,GAME);hid=choose(row,HOME);aid=choose(row,AWAY)
    start=utc(choose(row,START)); complete=utc(choose(row,FINAL))
    hs=num(choose(row,HP));aws=num(choose(row,AP))
    if not gid or not hid or not aid or hid==aid or not start or hs is None or aws is None:
        reasons['missing_id_start_or_score']+=1;return None
    verified=truth(choose(row,VERIFIED));neutral=truth(choose(row,VENUE))
    # A boolean site flag without independent verification is still unverified.
    if verified is not True or neutral is None:
        reasons['venue_not_independently_verified']+=1;return None
    if complete is None or complete < start:
        reasons['missing_or_bad_result_availability_time']+=1;return None
    div=choose(row,DIV)
    if 'women' in div.lower():div='womens-college-basketball'
    elif 'men' in div.lower():div='mens-college-basketball'
    else:
        low=str(source).lower()
        div='womens-college-basketball' if 'women' in low else 'mens-college-basketball' if 'men' in low else ''
    if not div:
        reasons['division_ambiguous']+=1;return None
    return dict(division=div,game_id=gid,home_id=hid,away_id=aid,start=start,available=complete,neutral=neutral,home_score=hs,away_score=aws,source=str(source))

def fit(train,ridge=8.,cap=40.,hca=3.):
    if len(train)<20:return {}
    tids=sorted({t for g in train for t in (g['home_id'],g['away_id'])})
    index={t:i for i,t in enumerate(tids)}
    n=len(tids);mat=np.eye(n)*ridge;vec=np.zeros(n)
    for g in train:
        i=index[g['home_id']];j=index[g['away_id']]
        m=np.clip(g['home_score']-g['away_score'],-cap,cap) - (0. if g['neutral'] else hca)
        mat[i,i]+=1;mat[j,j]+=1;mat[i,j]-=1;mat[j,i]-=1
        vec[i]+=m;vec[j]-=m
    values=np.linalg.solve(mat,vec)
    values-=values.mean()
    return dict(zip(tids,values))

def replay(games, max_predictions, max_train=4000):
    # Only objectively eligible games enter either training or evaluation.
    groups=defaultdict(list)
    for g in games:groups[g['division']].append(g)
    rows=[];stats={}
    for div, entries in sorted(groups.items()):
        entries.sort(key=lambda g:(g['start'],g['game_id']))
        eligible=0;skips=Counter();last_cutoff=None; ratings={}; train=[]
        for g in entries:
            if eligible>=max_predictions:break
            cutoff=g['start']-timedelta(minutes=1)
            # Completed game only usable once source's final-availability timestamp is earlier than cutoff.
            if cutoff!=last_cutoff:
                train=[p for p in entries if p['available']<cutoff and p['start']<cutoff]
                if len(train)>max_train:
                    skips['training_limit_reached']+=1
                    break
                ratings=fit(train)
                last_cutoff=cutoff
            if len(train)<20:
                skips['fewer_than_20_prior_finals']+=1;continue
            if g['home_id'] not in ratings or g['away_id'] not in ratings:
                skips['team_not_in_prior_fit']+=1;continue
            margin=float(ratings[g['home_id']]-ratings[g['away_id']]+(0 if g['neutral'] else 3))
            actual=g['home_score']-g['away_score']
            rows.append(dict(division=div,game_id=g['game_id'],scheduled_start_utc=g['start'].isoformat(),replay_cutoff_utc=cutoff.isoformat(),home_id=g['home_id'],away_id=g['away_id'],neutral_verified='true',neutral_site=str(g['neutral']).lower(),training_games=len(train),latest_training_result_available_utc=max(p['available'] for p in train).isoformat(),predicted_home_margin=round(margin,5),actual_home_margin=actual,absolute_margin_error=round(abs(margin-actual),5),source_path=g['source'],model='V114_ON_COURT_PROXY_NOT_PRODUCTION'))
            eligible+=1
        subset=[r for r in rows if r['division']==div]
        valid=[r for r in subset if r['actual_home_margin']!=0 and r['predicted_home_margin']!=0]
        stats[div]=dict(source_eligible_games=len(entries),predictions=len(subset),skipped=dict(skips),margin_mae=round(sum(r['absolute_margin_error'] for r in subset)/len(subset),4) if subset else None,winner_accuracy=round(sum((r['actual_home_margin']>0)==(r['predicted_home_margin']>0) for r in valid)/len(valid),4) if valid else None)
    return rows,stats

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--games',action='append',default=[]);p.add_argument('--out',default='data/historical_replay_v114');p.add_argument('--max-predictions',type=int,default=35);p.add_argument('--max-train-games',type=int,default=4000);a=p.parse_args()
    root=Path(a.root).resolve();out=Path(a.out);out=out if out.is_absolute() else root/out;out.mkdir(parents=True,exist_ok=True)
    sources=[Path(x) if Path(x).is_absolute() else root/x for x in a.games] if a.games else discover(root)
    rejection=Counter();inventory=[];accepted={};dup=Counter()
    for source in sources:
        if not source.exists():continue
        seen=0;ok=0
        try:
            for row in read_csv(source):
                seen+=1
                g=normalize(row,source.relative_to(root) if source.is_relative_to(root) else source,rejection)
                if g:
                    key=(g['division'],g['game_id'])
                    if key in accepted:
                        dup['duplicate_game_key']+=1
                        # Conflicts in duplicates cannot be resolved safely. Remove game from replay.
                        accepted[key]=None
                    else:accepted[key]=g
                    ok+=1
            inventory.append(dict(path=str(source.relative_to(root) if source.is_relative_to(root) else source),rows_seen=seen,eligible_rows_before_dedup=ok))
        except (UnicodeError,OSError,csv.Error,ValueError) as exc:
            inventory.append(dict(path=str(source),error=str(exc)[:160]))
    games=[g for g in accepted.values() if g is not None]
    rows,stats=replay(games,max(0,a.max_predictions),max(20,a.max_train_games))
    fields=['division','game_id','scheduled_start_utc','replay_cutoff_utc','home_id','away_id','neutral_verified','neutral_site','training_games','latest_training_result_available_utc','predicted_home_margin','actual_home_margin','absolute_margin_error','source_path','model']
    with (out/'predictions.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    summary=dict(version=114,status='RESEARCH_ONLY_STRICT_HISTORICAL_REPLAY' if rows else 'BLOCKED_AWAITING_VERIFIED_TIMESTAMPED_GAME_ROWS',production_modified=False,verified_input_rows=len(games),predictions=len(rows),rejections=dict(rejection),duplicates=dict(dup),divisions=stats,inputs=inventory,limitations=['Strict inputs need source-verified venue and timezone-aware result-availability timestamps.','Availability timestamps are supplied source claims and are not independently audited by this script.','Historical replay is not a real archived forecast and may contain upstream retrospective corrections.','On-court proxy only: no preseason priors, production blending, roster inputs, or coefficient search.','No model variant promotion; performance on this restricted sample is not production validation.'])
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    md=['# Courtside V114 — historical replay phase 1','','**RESEARCH ONLY — no production modifications.**','',f"Status: **{summary['status']}**",f"Strictly eligible input rows: **{len(games)}**",f"Reconstructed predictions: **{len(rows)}**",'', '## Division results']
    for div,s in stats.items():md.append(f"- {div}: {s['predictions']} predictions; MAE={s['margin_mae']}; winner accuracy={s['winner_accuracy']}; skips={s['skipped']}")
    md+=['','## Input rejection counts',f'`{dict(rejection)}`','','## Important','Do not treat this as a replay of full Courtside preseason-blended ratings. All results are retrospective reconstructions from documented available completed-game scores and verified site flags, not historical stored predictions.','', 'If no predictions are made, supply a source table with `division,game_id,game_start_utc,final_available_utc,home_id,away_id,home_points,away_points,neutral_site,neutral_verified`; do not fabricate `final_available_utc` or `neutral_verified`.']
    (out/'report.md').write_text('\n'.join(md)+'\n')
    print(json.dumps({'status':summary['status'],'eligible':len(games),'predictions':len(rows),'out':str(out)}))
if __name__=='__main__':main()

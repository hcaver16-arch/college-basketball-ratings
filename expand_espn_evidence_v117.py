#!/usr/bin/env python3
"""Courtside V117. Research-only resumable ESPN historical evidence expansion.

Never infers result-first-availability or independently verified venue.
"""
import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

SEASONS=('2024-25','2025-26')
DIVISIONS=('mens-college-basketball','womens-college-basketball')
COLUMNS=['season','division','game_id','archive_date','archive_home_id','archive_away_id','archive_home_points','archive_away_points','source_path','espn_url','retrieved_utc','response_sha256','outcome','http_status','espn_start_utc','espn_date_eastern','eastern_date_matches_archive','espn_home_id','espn_away_id','espn_home_points','espn_away_points','team_ids_match','scores_match','espn_neutral_site','archived_venue_text','archived_neutral_label','venue_label_comparison','espn_completed','date_disagreement','duplicate_conflict','final_available_utc','independently_verified_venue','eligible_strict_replay','warnings']

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

def load_games(root,per_stratum):
    selected=[]; stats={}; all_2025={}; conflicts=Counter()
    for season in SEASONS:
      for div in DIVISIONS:
        label='mens' if div.startswith('mens') else 'womens'
        path=root/'data'/'historical_efficiency'/f'{season}_{label}_paired_games.csv.gz'
        key=f'{season}/{label}'
        stats[key]={'source':str(path.relative_to(root)),'exists':path.exists(),'valid_rows':0,'conflicts':0,'target':0}
        if not path.exists(): continue
        rows={}; invalid=set()
        for r in csvrows(path):
            gid=normid(r.get('game_id')); hid=normid(r.get('home_id')); aid=normid(r.get('away_id'))
            hp=num(r.get('home_points')); ap=num(r.get('away_points')); date=str(r.get('date') or '')[:10]
            if not (gid.isdigit() and hid and aid and hp is not None and ap is not None and re.fullmatch(r'\d{4}-\d{2}-\d{2}',date)): continue
            row={'season':season,'division':div,'game_id':gid,'archive_date':date,'archive_home_id':hid,'archive_away_id':aid,'archive_home_points':hp,'archive_away_points':ap,'source_path':str(path.relative_to(root))}
            if gid in rows and row != rows[gid]:invalid.add(gid)
            rows[gid]=row
        for gid in invalid:rows.pop(gid,None)
        stats[key]['conflicts']=len(invalid)
        ordered=sorted(rows.values(),key=lambda x:(x['archive_date'],x['game_id']))
        stats[key]['valid_rows']=len(ordered)
        if not ordered:continue
        if len(ordered)<=per_stratum: sample=ordered
        elif per_stratum==1: sample=[ordered[len(ordered)//2]]
        else: sample=[ordered[(i*(len(ordered)-1))//(per_stratum-1)] for i in range(per_stratum)]
        stats[key]['target']=len(sample)
        selected+=sample
        if season=='2025-26':all_2025[div]=rows
    return selected,stats,all_2025

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

def run(args):
    root=Path(args.root).resolve(); output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True)
    target,source_stats,_=load_games(root,args.per_stratum)
    archived_venues,venue_conflicts=archive_venues(root)
    path=output/'evidence.csv'; stored=load_checkpoint(path); target_keys={(x['season'],x['division'],x['game_id']) for x in target}
    # Only retry failures if explicitly requested: successful historical observations stay frozen.
    pending=[x for x in target if ((x['season'],x['division'],x['game_id']) not in stored or (args.retry_failed and stored[(x['season'],x['division'],x['game_id'])].get('outcome')!='ok'))]
    pending=pending[:args.max_new]
    fetched=Counter()
    for n,item in enumerate(pending,1):
        url=f'https://site.api.espn.com/apis/site/v2/sports/basketball/{item["division"]}/summary?event={item["game_id"]}'
        rec={x:'' for x in COLUMNS};rec.update(item);rec['espn_url']=url;rec['retrieved_utc']=now()
        data,outcome,sha,code=retrieve(url,args.timeout,args.retries,args.pause)
        rec.update({'outcome':outcome,'response_sha256':sha,'http_status':code,'final_available_utc':'','independently_verified_venue':False,'eligible_strict_replay':False})
        if outcome=='ok':rec.update(interpret(data,item,archived_venues,venue_conflicts))
        else:rec['warnings']='no_usable_provider_response'
        stored[(item['season'],item['division'],item['game_id'])]=rec
        fetched[outcome]+=1
        # Checkpoint after EACH request; archive remains valid on interruption.
        write_csv(path,[stored[k] for k in sorted(stored)])
        if n<len(pending) and args.pause:time.sleep(args.pause)
    chosen=[stored[k] for k in sorted(target_keys) if k in stored]
    for k,v in stored.items():
        if k not in target_keys:pass # preserved across expanded or smaller selection
    count=Counter(x.get('outcome','') for x in chosen)
    comparisons=Counter(x.get('venue_label_comparison','') for x in chosen if x.get('outcome')=='ok')
    date_mismatches=[x for x in chosen if str(x.get('date_disagreement')).lower()=='true']
    id_mismatches=[x for x in chosen if x.get('outcome')=='ok' and str(x.get('team_ids_match')).lower()!='true']
    score_mismatches=[x for x in chosen if x.get('outcome')=='ok' and str(x.get('scores_match')).lower()!='true']
    venue_disagreements=[x for x in chosen if x.get('venue_label_comparison') in ('labels_disagree','archive_venue_internal_conflict')]
    for name,records in [('venue_disagreements.csv',venue_disagreements),('date_disagreements.csv',date_mismatches),('team_or_score_conflicts.csv',list({(r['division'],r['game_id']):r for r in id_mismatches+score_mismatches}.values()))]:
        write_csv(output/name,records)
    summary={'version':117,'status':'RESEARCH_ONLY_RESUMABLE_ESPN_EVIDENCE','generated_utc':now(),'production_modified':False,
        'target_per_stratum':args.per_stratum,'max_new_per_run':args.max_new,'source_stats':source_stats,
        'target_games':len(target),'checkpoint_total_records':len(stored),'target_records_present':len(chosen),
        'target_remaining':len(target)-len(chosen),'new_requests_this_run':len(pending),'new_outcomes_this_run':dict(fetched),
        'all_outcomes':dict(count),'team_id_mismatches':len(id_mismatches),'score_mismatches':len(score_mismatches),
        'eastern_date_disagreements':len(date_mismatches),'venue_label_comparison':dict(comparisons),
        'independent_venue_verified':0,'first_final_availability_verified':0,'strict_replay_eligible':0,
        'warnings':['Retrospective ESPN response is not a record of first result publication.',
          'ESPN neutralSite and archived Venue originate from data feeds that may be dependent; agreement is not independent corroboration.',
          'America/New_York date is a comparison convention, not proof archive dates are ET.',
          'Resuming needs evidence.csv persisted in research output directory between GitHub Actions runs.',
          'No replay scoring or model tuning authorized.']}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    lines=['# Courtside V117 historical evidence expansion','', '**Research only. No production ratings/site/predictions altered.**','',
        f'Games targeted: **{len(target)}**; checkpoint records for target: **{len(chosen)}**; remaining **{len(target)-len(chosen)}**.',
        f'New ESPN requests this run: **{len(pending)}**.','',
        '## Provider outcomes','']+[f'- {k}: {v}' for k,v in sorted(count.items())]+['','## Venue comparisons','']+[f'- {k}: {v}' for k,v in sorted(comparisons.items())]+['',
        f'Eastern date disagreements: **{len(date_mismatches)}**. Team ID mismatches: **{len(id_mismatches)}**; score mismatches: **{len(score_mismatches)}**.','',
        '**Strict historical replay eligible: 0**. Neither historical first-final availability timestamps nor independently verified neutral-site classifications are established.','',
        'See evidence.csv and the three discrepancy reports. Commit only the research checkpoint to preserve progress.']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return summary

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default='.')
    p.add_argument('--output',default='data/game_evidence_v117')
    p.add_argument('--per-stratum',type=int,default=200)
    p.add_argument('--max-new',type=int,default=200)
    p.add_argument('--retry-failed',action='store_true')
    p.add_argument('--pause',type=float,default=0.35)
    p.add_argument('--timeout',type=float,default=15)
    p.add_argument('--retries',type=int,default=2)
    args=p.parse_args()
    if not 1<=args.per_stratum<=1500:p.error('per-stratum out of range')
    if not 1<=args.max_new<=1000:p.error('max-new out of range')
    if args.pause<0 or args.timeout<=0 or not 0<=args.retries<=5:p.error('invalid fetch parameters')
    print(json.dumps(run(args),indent=2))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Courtside V116: ESPN evidence recovery for sampled historical games. Research only."""
import argparse, csv, gzip, hashlib, io, json, math, os, random, re, sys, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DIVISIONS = ('mens-college-basketball', 'womens-college-basketball')
SEASONS = ('2024-25', '2025-26')
FIELDS = ['season','division','game_id','archive_date','archive_home_id','archive_away_id','archive_home_points','archive_away_points',
          'espn_event_url','retrieved_utc','response_sha256','http_status','outcome','espn_game_start_utc','espn_home_id',
          'espn_away_id','espn_home_points','espn_away_points','espn_status','espn_completed','espn_neutral_site',
          'team_ids_match','scores_match','date_match','venue_evidence_status','game_start_evidence_status',
          'final_available_utc','final_available_evidence_status','eligible_for_strict_replay','warnings']

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def val(x): return '' if x is None else str(x).strip()
def numeric_id(x):
    s=val(x)
    return str(int(s)) if re.fullmatch(r'\d+(?:\.0+)?',s) else s

def iso_utc(s):
    s=val(s)
    if not s: return ''
    try:
        dt=datetime.fromisoformat(s.replace('Z','+00:00'))
        if dt.tzinfo is None: return ''
        return dt.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
    except ValueError: return ''

def number(x):
    try:
        f=float(x)
        return f if math.isfinite(f) else None
    except (ValueError,TypeError): return None

def selected_games(root, per_stratum):
    selected=[]; stats={}
    for season in SEASONS:
        for division in DIVISIONS:
            tag='mens' if division.startswith('mens') else 'womens'
            path=root/'data'/'historical_efficiency'/f'{season}_{tag}_paired_games.csv.gz'
            k=f'{season}/{tag}'
            stats[k]={'source':str(path.relative_to(root)), 'found':path.is_file(), 'valid_unique_rows':0,'invalid_rows':0,'sampled':0}
            if not path.is_file(): continue
            games={}
            with gzip.open(path,'rt',encoding='utf-8-sig',newline='') as f:
                for row in csv.DictReader(f):
                    game_id=numeric_id(row.get('game_id'))
                    day=val(row.get('date'))[:10]
                    h=numeric_id(row.get('home_id')); a=numeric_id(row.get('away_id'))
                    hp=number(row.get('home_points')); ap=number(row.get('away_points'))
                    if not (game_id.isdigit() and re.fullmatch(r'\d{4}-\d\d-\d\d',day) and h and a and hp is not None and ap is not None):
                        stats[k]['invalid_rows']+=1; continue
                    item={'season':season,'division':division,'game_id':game_id,'archive_date':day,'archive_home_id':h,
                          'archive_away_id':a,'archive_home_points':hp,'archive_away_points':ap}
                    if game_id in games and item!=games[game_id]:
                        stats[k].setdefault('conflicting_duplicate_ids',0)
                        stats[k]['conflicting_duplicate_ids']+=1
                        games.pop(game_id,None)
                        continue
                    games[game_id]=item
            rows=sorted(games.values(),key=lambda r:(r['archive_date'],r['game_id']))
            stats[k]['valid_unique_rows']=len(rows)
            # Spread evenly across the season, deterministically, so sampling does not center on opening month.
            if len(rows)<=per_stratum: chosen=rows
            elif per_stratum==1: chosen=[rows[len(rows)//2]]
            else:
                ids=[(i*(len(rows)-1))//(per_stratum-1) for i in range(per_stratum)]
                chosen=[rows[i] for i in ids]
            stats[k]['sampled']=len(chosen)
            selected.extend(chosen)
    return selected,stats

def fetch(url, timeout, retries, pause, opener=None):
    opener=opener or urlopen
    for attempt in range(retries+1):
        try:
            req=Request(url,headers={'User-Agent':'CourtsideResearchEvidenceAudit/116 (public academic sample)','Accept':'application/json'})
            with opener(req,timeout=timeout) as response:
                payload=response.read(5_000_001)
                if len(payload)>5_000_000: return {},'response_too_large','',0
                data=json.loads(payload.decode('utf-8'))
                return data,'ok',hashlib.sha256(payload).hexdigest(),200
        except HTTPError as e:
            status=e.code
            if status in (429,500,502,503,504) and attempt<retries:
                time.sleep(pause*(attempt+1));continue
            return {},f'http_{status}','',status
        except (URLError,TimeoutError,OSError,ValueError,json.JSONDecodeError) as e:
            if attempt<retries: time.sleep(pause*(attempt+1)); continue
            return {},f'fetch_error_{type(e).__name__}','',''
    return {},'retry_exhausted','',''

def get_comp(data):
    header=data.get('header') if isinstance(data.get('header'),dict) else {}
    competitions=header.get('competitions') or []
    comp=competitions[0] if competitions and isinstance(competitions[0],dict) else {}
    return header,comp

def extract(data, r):
    h,comp=get_comp(data)
    warnings=[]
    competitors=comp.get('competitors') or []
    sides={}
    for c in competitors:
        if not isinstance(c,dict): continue
        side=val(c.get('homeAway')).lower()
        team=c.get('team') or {}
        if side in ('home','away') and isinstance(team,dict):
            sides[side]={'id':numeric_id(team.get('id')),'score':number(c.get('score'))}
    found_date=iso_utc(comp.get('date') or h.get('date'))
    result={'espn_game_start_utc':found_date,
       'espn_home_id':sides.get('home',{}).get('id',''),'espn_away_id':sides.get('away',{}).get('id',''),
       'espn_home_points':sides.get('home',{}).get('score',''),'espn_away_points':sides.get('away',{}).get('score','')}
    typ=(comp.get('status') or h.get('status') or {}).get('type') or {}
    result['espn_status']=val(typ.get('name') or typ.get('description'))
    result['espn_completed']=typ.get('completed') if type(typ.get('completed')) is bool else ''
    neutral=comp.get('neutralSite')
    result['espn_neutral_site']=neutral if type(neutral) is bool else ''
    ids_match=bool(result['espn_home_id'] and result['espn_away_id'] and result['espn_home_id']==r['archive_home_id'] and result['espn_away_id']==r['archive_away_id'])
    result['team_ids_match']=ids_match
    scores_match=(result['espn_home_points'] is not None and result['espn_away_points'] is not None and
       result['espn_home_points']==r['archive_home_points'] and result['espn_away_points']==r['archive_away_points'])
    result['scores_match']=scores_match
    result['date_match']=bool(found_date and found_date[:10]==r['archive_date'])
    if found_date and not result['date_match']: warnings.append('UTC calendar date differs from archive date; timezone may explain, requires review')
    if not ids_match: warnings.append('ESPN home/away team IDs disagree or are absent')
    if not scores_match: warnings.append('ESPN final score differs or is absent')
    if result['espn_completed'] is not True: warnings.append('ESPN does not explicitly mark event completed')
    # ESPN is provider-reported, not independently venue-verified by second source.
    result['venue_evidence_status']='ESPN_REPORTED_NOT_INDEPENDENTLY_VERIFIED' if type(neutral) is bool else 'MISSING'
    result['game_start_evidence_status']='ESPN_REPORTED_RETRIEVED_RETROSPECTIVELY' if found_date else 'MISSING'
    result['final_available_utc']=''
    result['final_available_evidence_status']='UNAVAILABLE_ESPN_CURRENT_SUMMARY_NOT_HISTORICAL_FIRST_OBSERVED'
    result['eligible_for_strict_replay']=False
    result['warnings']='; '.join(warnings)
    return result

def run(args, opener=None):
    root=Path(args.root).resolve(); out=Path(args.output).resolve(); out.mkdir(parents=True,exist_ok=True)
    selected,source_stats=selected_games(root,args.per_stratum)
    results=[]; errors=Counter()
    for index,r in enumerate(selected):
        url=f'https://site.api.espn.com/apis/site/v2/sports/basketball/{r["division"]}/summary?'+urlencode({'event':r['game_id']})
        record={key:'' for key in FIELDS};record.update(r)
        record['espn_event_url']=url;record['retrieved_utc']=now()
        data,outcome,sha,status=fetch(url,args.timeout,args.retries,args.pause,opener)
        record['outcome']=outcome;record['response_sha256']=sha;record['http_status']=status
        if outcome=='ok' and isinstance(data,dict): record.update(extract(data,r))
        else:
            record['final_available_evidence_status']='UNAVAILABLE'
            record['eligible_for_strict_replay']=False
            record['warnings']='No usable ESPN event data returned'
        errors[outcome]+=1;results.append(record)
        if index<len(selected)-1 and args.pause>0: time.sleep(args.pause)
    with (out/'evidence.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS,extrasaction='ignore');writer.writeheader();writer.writerows(results)
    summary={'version':116,'status':'RESEARCH_ONLY_ESPN_GAME_EVIDENCE_RECOVERY','generated_utc':now(),
       'production_modified':False,'sample_policy':'Deterministic season-spread sample per 4 season/division strata',
       'per_stratum_requested':args.per_stratum,'source_stats':source_stats,'sampled_game_count':len(selected),
       'responses':dict(errors),'team_id_matches':sum(r.get('team_ids_match') is True for r in results),
       'score_matches':sum(r.get('scores_match') is True for r in results),
       'espn_neutral_site_reported':sum(type(r.get('espn_neutral_site')) is bool for r in results),
       'espn_start_utc_reported':sum(bool(r.get('espn_game_start_utc')) for r in results),
       'final_availability_verified':0,'independent_venue_verified':0,'strict_replay_eligible':0,
       'limits':['ESPN current game summaries are retrospective source snapshots; no original historical response capture established.',
        'ESPN event date and neutralSite are provider-reported; they do not independently verify the venue.',
        'ESPN status completed is not a final-result publication timestamp; never infer final_available_utc from event or plays.',
        'No new historical forecast or parameter tuning authorized.','Do not feed evidence.csv into V114 without independent venue and availability validation.',
        'Archive UTC game dates can differ from local date; mismatches are flagged, not overwritten.']}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    lines=['# Courtside V116 — historical ESPN evidence recovery','', '**Research-only; production data untouched.**','',
      f'Sampled games: **{len(selected)}** (up to {args.per_stratum} per season/division).',
      f'ESPN responses OK: **{errors.get("ok",0)}**.',
      f'Game-start timestamps reported: **{summary["espn_start_utc_reported"]}**.',
      f'Neutral-site values reported: **{summary["espn_neutral_site_reported"]}**.',
      f'Matching team IDs: **{summary["team_id_matches"]}**; matching scores: **{summary["score_matches"]}**.','',
      '## Critical provenance limitation','',
      'Historical final-result availability times were **not** recovered. Current ESPN status and response time cannot prove when the final first became available. Venue is ESPN-reported, not independently verified. Therefore **zero games are authorized for strict V114 replay**.','',
      '## Provider responses','']
    for k,v in sorted(errors.items()):lines.append(f'- `{k}`: {v}')
    lines+=['','## Source strata','']
    for key,st in source_stats.items(): lines.append(f'- {key}: source found={st["found"]}, valid unique={st["valid_unique_rows"]}, sampled={st["sampled"]}')
    lines+=['','See `evidence.csv` for exact ESPN source URLs, retrieval times, response hashes, mismatches and explicit missing fields.']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return summary

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default='.')
    p.add_argument('--output',default='data/game_evidence_v116')
    p.add_argument('--per-stratum',type=int,default=12)
    p.add_argument('--pause',type=float,default=1.2)
    p.add_argument('--timeout',type=float,default=15)
    p.add_argument('--retries',type=int,default=2)
    args=p.parse_args()
    if not 1<=args.per_stratum<=40: p.error('--per-stratum must be between 1 and 40')
    if args.pause<0 or args.timeout<=0 or not 0<=args.retries<=5:p.error('invalid request limits')
    print(json.dumps(run(args),indent=2))
if __name__=='__main__':main()

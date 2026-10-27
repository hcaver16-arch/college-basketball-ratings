#!/usr/bin/env python3
"""Courtside V108: evidence-labeled D1 basketball universe and fallback audit.

Read-only with respect to production; only writes data/d1_repair_v108.
No automatic classifications of baseline-only schools as non-D1.
"""
import argparse, csv, json, math
from datetime import datetime,timezone
from pathlib import Path
from collections import Counter

DIVS=('mens-college-basketball','womens-college-basketball')
SOURCE_ASUN='https://asunsports.org/news/2026/7/16/atlantic-sun-conference-announces-2026-27-mens-womens-basketball-schedules.aspx'
SOURCE_NCAA='https://web3.ncaa.org/directory/orgDetail?id=11740'
SOURCE_MEMBERS='https://www.ncaa.org/about-us/membership-directory/membership-composition-and-sport-sponsorship/'
# Conference-issued 2026-27 BOTH men's and women's schedule, verified July 16, 2026.
# NCAA active membership is NOT inferred from this league competition evidence.
ASUN={
 'Bellarmine':('Bellarmine',),
 'Florida Gulf Coast':('Florida Gulf Coast','FGCU'),
 'Jacksonville':('Jacksonville Dolphins',),
 'Lipscomb':('Lipscomb',),
 'North Florida':('North Florida',),
 'Queens':('Queens',),
 'Stetson':('Stetson',),
 'West Florida':('West Florida',),
}

def load(path):
 with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def save(path,rows,columns):
 path.parent.mkdir(parents=True,exist_ok=True)
 with open(path,'w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(rows)
def num(x):
 try:
  z=float(x);return z if math.isfinite(z) else None
 except(TypeError,ValueError):return None
def asbool(v):return str(v).lower().strip() in ('true','1','yes')
def find(rows,division):return [r for r in rows if r.get('division')==division]
def norm(s):return ''.join(c for c in str(s).casefold() if c.isalnum())
def unique(rows,division):
 out={}
 for r in find(rows,division):
  id=str(r.get('team_id','')).strip()
  if not id or id in out:raise ValueError('Missing/duplicate ESPN ID for '+division+': '+id)
  out[id]=r
 return out

def classify(team,div):
 key=norm(team)
 for school,names in ASUN.items():
  if any(norm(n) in key or key==norm(n) for n in names):
   # Prevent substring overmatch by names like Jacksonville State or unrelated Stetson.
   if school=='Jacksonville' and 'state' in key:continue
   if school=='West Florida':return 'reclassifying_d1_basketball','conference_and_ncaa_directory',SOURCE_ASUN+' | '+SOURCE_NCAA
   return 'conference_confirmed_d1_basketball','conference_schedule_2026_27',SOURCE_ASUN
 return 'unverified_candidate','roster_archive_only',''

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--audit-dir',type=Path,default=Path('data/d1_audit_v107'))
 ap.add_argument('--out',type=Path,default=Path('data/d1_repair_v108'))
 ap.add_argument('--reviewed-csv',type=Path,help='Optional explicit reviewed CSV: division,team_id,status,source_url,note. Valid status: confirmed_d1_basketball, reclassifying_d1_basketball, excluded_non_d1, needs_review. Must cite an independent source.')
 args=ap.parse_args()
 args.out.mkdir(parents=True,exist_ok=True)
 reviewed={}
 if args.reviewed_csv:
  for r in load(args.reviewed_csv):
   key=(r.get('division',''),str(r.get('team_id','')).strip())
   status=r.get('status','').strip()
   if key[0] not in DIVS or not key[1] or status not in ('confirmed_d1_basketball','reclassifying_d1_basketball','excluded_non_d1','needs_review'):
    raise ValueError('Invalid reviewed membership: '+str(r))
   if status in ('confirmed_d1_basketball','reclassifying_d1_basketball','excluded_non_d1') and not (r.get('source_url') or '').startswith('https://'):
    raise ValueError('Independent source_url mandatory for membership classification '+str(key))
   if key in reviewed:raise ValueError('Duplicate reviewed row '+str(key))
   reviewed[key]=r
 result={'version':108,'generated_at_utc':datetime.now(timezone.utc).isoformat(),'status':'RESEARCH_ONLY_PARTIAL_SOURCE_VERIFICATION','production_modified':False,'complete_authoritative_2026_27_list':False,'source_references':[SOURCE_ASUN,SOURCE_NCAA,SOURCE_MEMBERS],'cautions':['NCAA reports 361 active DI institutions as of Sep 2026; figure is not a list of all basketball-participating transition schools','ASUN conference appearance is verified basketball participation, NOT proof of active NCAA Division I membership','No unverified archive or baseline-only entry is automatically promoted to verified or excluded','Fallback ratings are research-only proposals and must not be interpreted as learned player talent','No official ranking changes, prediction changes, or historical accuracy claims'],'divisions':{}}
 for div in DIVS:
  members_path=args.audit_dir/(div+'_membership_audit.csv')
  comp_path=args.audit_dir/(div+'_research_comparison.csv')
  if not members_path.exists() or not comp_path.exists():raise FileNotFoundError('Run V107 first; missing '+str(members_path if not members_path.exists() else comp_path))
  a=unique(load(members_path),div);c=unique(load(comp_path),div)
  records=[]
  for tid,r in a.items():
   name=r.get('team') or ''
   status,method,source=classify(name,div)
   if status=='unverified_candidate' and not asbool(r.get('in_v105')):
    status,method,source='baseline_only_needs_review','baseline_archive_only',''
   review=reviewed.get((div,tid))
   if review:
    status=review['status'];method='explicit_review';source=review.get('source_url','')
   bas=num(r.get('saved_rating'));adj=num(r.get('roster_adjustment'))
   if not asbool(r.get('has_usable_roster_signal')):adj=None
   records.append({'division':div,'team_id':tid,'team':name,'membership_status':status,'evidence_method':method,'source_url':source,'review_note':review.get('note','') if review else '',
                   'in_roster_archive':asbool(r.get('in_v105')),'in_baseline':asbool(r.get('in_v106')),'baseline_rating':bas,
                   'has_roster_evidence':adj is not None,'illustrative_adjustment':adj,'research_rating':(bas+adj if bas is not None and adj is not None else bas),
                   'unavailable_rating':bas is None,'warning':r.get('roster_quality_warning') or ''})
  # source-confirmed ASUN count verification, no silent gaps.
  confirmed=[r for r in records if r['membership_status'] in ('conference_confirmed_d1_basketball','confirmed_d1_basketball','reclassifying_d1_basketball')]
  missing_baseline=[r for r in confirmed if r['baseline_rating'] is None]
  # Fallback: strictly diagnostic reference: median baseline rating of 7 verified ASUN peers, not trained or adopted.
  peers=sorted(r['baseline_rating'] for r in confirmed if r['baseline_rating'] is not None and r['team'] and norm(r['team'])!=norm('West Florida'))
  peer_median=(peers[len(peers)//2] if len(peers)%2 else (peers[len(peers)//2-1]+peers[len(peers)//2])/2) if len(peers)>=3 else None
  fallbacks=[]
  for r in missing_baseline:
   fallbacks.append({'division':div,'team_id':r['team_id'],'team':r['team'],'baseline_rating':'','fallback_proposal':peer_median,'fallback_type':'ASUN_peer_median_UNVALIDATED_RESEARCH_ONLY' if peer_median is not None else 'not_available','peer_count':len(peers),'warning':'Not a live rating; does not model D2 performance, recruiting, or talent; requires prospective validation'})
  cols=['division','team_id','team','membership_status','evidence_method','source_url','review_note','in_roster_archive','in_baseline','baseline_rating','has_roster_evidence','illustrative_adjustment','research_rating','unavailable_rating','warning']
  save(args.out/(div+'_membership_evidence.csv'),records,cols)
  save(args.out/(div+'_missing_rating_fallback_proposals.csv'),fallbacks,['division','team_id','team','baseline_rating','fallback_proposal','fallback_type','peer_count','warning'])
  # Compare using only backed baseline and conference participation verification, not all candidates.
  compare=sorted([dict(r) for r in confirmed if r['baseline_rating'] is not None],key=lambda r:(-r['baseline_rating'],r['team_id']))
  b_ranks={r['team_id']:i+1 for i,r in enumerate(compare)}
  x_ranks={r['team_id']:i+1 for i,r in enumerate(sorted(compare,key=lambda r:(-r['research_rating'],r['team_id'])))}
  for r in compare:r.update(baseline_rank=b_ranks[r['team_id']],experimental_rank=x_ranks[r['team_id']],rank_change=b_ranks[r['team_id']]-x_ranks[r['team_id']])
  save(args.out/(div+'_source_confirmed_research_comparison.csv'),compare,cols+['baseline_rank','experimental_rank','rank_change'])
  counts=Counter(r['membership_status'] for r in records)
  result['divisions'][div]={'records_reviewed':len(records),'source_confirmed_basketball_participants':len(confirmed),'status_counts':dict(counts),'confirmed_missing_baseline':[{'team':r['team'],'team_id':r['team_id']} for r in missing_baseline],'research_fallback_proposals':len(fallbacks),'source_confirmed_comparison_teams':len(compare),'fallback_asun_peer_reference':peer_median,'unreviewed_baseline_only':counts['baseline_only_needs_review'],'unverified_roster_candidates':counts['unverified_candidate'],'minimum_expected_asun_teams':8,'asun_evidence_coverage_warning':None if len([r for r in records if 'asunsports.org' in r['source_url']])>=8 else 'Some ASUN IDs absent or not recognized: check alias matching; do not claim complete validation'}
 (args.out/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(result,indent=2))

if __name__=='__main__':main()

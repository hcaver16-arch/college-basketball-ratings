#!/usr/bin/env python3
"""Courtside V107 research-only D1 universe reconciliation.

No production ratings, predictions, canonical lists or live UI are written.
A 2026-27 roster archive is a CANDIDATE list, not proof of NCAA membership.
"""
import argparse
import csv
import gzip
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DIVISIONS = ('mens-college-basketball', 'womens-college-basketball')
V105 = Path('data/roster_experiment_v105')
V106 = Path('data/baseline_comparison_v106')
OUT = Path('data/d1_audit_v107')

def read_csv(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8-sig', newline='') as fp:
        return list(csv.DictReader(fp))

def find_csv(folder, division, prefer=()):
    if not folder.exists(): return None
    options = [p for p in folder.rglob('*') if p.is_file() and p.suffix == '.csv' and division in p.name]
    if not options: return None
    return sorted(options, key=lambda p: (-sum(token in p.name.lower() for token in prefer),len(p.parts),str(p)))[0]

def number(x):
    try: return float(x)
    except (ValueError, TypeError): return None

def truth(x): return str(x).strip().lower() in ('true','1','yes')

def team_id(row): return str(row.get('team_id') or '').strip()

def write_csv(path, rows, cols):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)

def ranks(items,key):
    ordered=sorted(items,key=lambda r:(-r[key],r['team_id']))
    # stable sequential rank; IDs unique, ties decided by ID
    return {r['team_id']:i+1 for i,r in enumerate(ordered)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--v105-dir',type=Path,default=V105);p.add_argument('--v106-dir',type=Path,default=V106)
    p.add_argument('--out',type=Path,default=OUT)
    p.add_argument('--canonical-csv',type=Path,default=None,help='Optional independently reviewed 2026-27 membership CSV: division,team_id,status (verified_d1/excluded/needs_review)')
    a=p.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
    verified={};excluded={};review={}
    if a.canonical_csv:
        for r in read_csv(a.canonical_csv):
            key=(str(r.get('division','')).strip(),team_id(r)); status=str(r.get('status','')).strip().lower()
            if not key[0] in DIVISIONS or not key[1] or status not in ('verified_d1','excluded','needs_review'):
                raise SystemExit('Invalid canonical membership row: '+str(r))
            if key in verified or key in excluded or key in review: raise SystemExit('Duplicate membership: '+str(key))
            {'verified_d1':verified,'excluded':excluded,'needs_review':review}[status][key]=r
    summary={'version':107,'generated_at_utc':datetime.now(timezone.utc).isoformat(),'status':'RESEARCH_ONLY_MEMBERSHIP_AUDIT','membership_source':'explicit_reviewed_csv' if a.canonical_csv else 'V105_ROSTER_CANDIDATE_NOT_INDEPENDENTLY_VERIFIED','canonical_csv':str(a.canonical_csv) if a.canonical_csv else None,'production_modified':False,'cautions':['Archive inclusion is NOT verified D1 membership; unverified teams are candidates only','Baseline-only team IDs can be legitimate D1 and must not be automatically excluded','Missing roster signals are NOT evidence of zero talent','Rank changes are sensitivity only, never predictive-validation evidence'],'divisions':{}}
    for division in DIVISIONS:
        v105path=find_csv(a.v105_dir,division,('team','experiment'))
        v106path=find_csv(a.v106_dir,division,('comparison','baseline'))
        if not v105path or not v106path: raise SystemExit(f'Missing V105/V106 CSV for {division}: {v105path}; {v106path}')
        roster=read_csv(v105path); baseline=read_csv(v106path)
        def unique(rows,tag):
            ids=[team_id(x) for x in rows]; duplicates=[x for x,n in Counter(ids).items() if n>1 or not x]
            if duplicates: raise SystemExit(f'{tag} duplicate/blank IDs: {duplicates[:15]}')
            return {team_id(r):r for r in rows}
        v=unique(roster,'v105'); b=unique(baseline,'v106')
        members=[]; candidates=[]; exclusions=[]
        for tid in sorted(set(v)|set(b),key=lambda x:(len(x),x)):
            r=v.get(tid,{}); q=b.get(tid,{})
            key=(division,tid)
            status='verified_d1' if key in verified else 'excluded' if key in excluded else 'needs_review' if key in review else 'roster_candidate_unverified' if tid in v else 'baseline_only_needs_review'
            baseline_rating=number(q.get('baseline_rating'))
            adjusted=number(r.get('illustrative_adjustment_points'))
            usable=bool(tid in v and truth(r.get('data_available')) and adjusted is not None)
            warning=str(r.get('quality_warning') or '').strip()
            record={'division':division,'team_id':tid,'team':r.get('team') or q.get('baseline_team') or q.get('team') or '', 'membership_status':status,'in_v105':tid in v,'in_v106':tid in b,'saved_rating':baseline_rating,'has_usable_roster_signal':usable,'roster_adjustment':adjusted if usable else None,'roster_quality_warning':warning,'review_note':(verified.get(key) or excluded.get(key) or review.get(key) or {}).get('note','')}
            members.append(record)
            if status=='verified_d1': candidates.append(record)
            elif status=='excluded': exclusions.append(record)
        # Candidate-only comparison is explicitly NOT verified D1 ranking.
        universe=candidates if a.canonical_csv else [m for m in members if m['in_v105']]
        matched=[m for m in universe if m['saved_rating'] is not None]
        scored=[]
        for item in matched:
            item=dict(item)
            item['experimental_rating']=item['saved_rating']+(item['roster_adjustment'] or 0)
            item['research_adjustment']=item['roster_adjustment'] or 0
            scored.append(item)
        base_ranks=ranks(scored,'saved_rating');exp_ranks=ranks(scored,'experimental_rating')
        for item in scored:
            tid=item['team_id'];item['baseline_rank']=base_ranks[tid];item['experimental_rank']=exp_ranks[tid];item['rank_change']=base_ranks[tid]-exp_ranks[tid]
        cols=['division','team_id','team','membership_status','in_v105','in_v106','saved_rating','has_usable_roster_signal','roster_adjustment','roster_quality_warning','review_note']
        rankcols=cols+['research_adjustment','experimental_rating','baseline_rank','experimental_rank','rank_change']
        write_csv(a.out/f'{division}_membership_audit.csv',members,cols)
        write_csv(a.out/f'{division}_research_comparison.csv',sorted(scored,key=lambda r:r['baseline_rank']),rankcols)
        changes=sorted(scored,key=lambda r:(-abs(r['rank_change']),r['team']))[:15]
        summary['divisions'][division]={'v105_archive_candidates':len(v),'v106_baseline_records':len(b),'both':len(set(v)&set(b)),'baseline_only_needs_review':sum(m['membership_status']=='baseline_only_needs_review' for m in members),'candidate_only_no_baseline':len(set(v)-set(b)),'canonical_verified':sum(m['membership_status']=='verified_d1' for m in members),'canonical_excluded':len(exclusions),'unverified_candidates':sum(m['membership_status']=='roster_candidate_unverified' for m in members),'research_universe':'verified_d1_only' if a.canonical_csv else 'v105_roster_candidates_UNVERIFIED','research_universe_teams':len(universe),'comparison_teams_with_baseline':len(scored),'max_absolute_rank_change':max((abs(r['rank_change']) for r in scored),default=None),'mean_absolute_research_adjustment':(round(sum(abs(r['research_adjustment']) for r in scored)/len(scored),5) if scored else None),'largest_movements':[{'team':r['team'],'before':r['baseline_rank'],'after':r['experimental_rank'],'change':r['rank_change']} for r in changes],'source_files':{'v105':str(v105path),'v106':str(v106path)}}
    (a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()

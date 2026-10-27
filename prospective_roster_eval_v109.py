#!/usr/bin/env python3
"""Courtside V109: append-only, paired prospective roster evaluation.

Reads V97 official pregame forecasts/results and V105 adjustment CSVs; never alters
live ratings. Builds one prospective paired research record per (division, game).
"""
import argparse,csv,hashlib,json,math,os
from pathlib import Path
from datetime import datetime,timezone,timedelta
from collections import defaultdict

DIVS=('mens','womens')
FIELDS=['season','division','game_id','game_start_utc','home_id','away_id','home_team','away_team','neutral',
        'baseline_model_id','baseline_forecast_created_utc','paired_created_utc','ratings_snapshot_utc',
        'baseline_snapshot_sha256','roster_snapshot_created_utc','roster_snapshot_sha256',
        'baseline_predicted_home_margin','home_roster_adjustment','away_roster_adjustment',
        'experimental_predicted_home_margin','model_id','experiment_note']

def utc(s):
 try:
  d=datetime.fromisoformat(str(s).replace('Z','+00:00'))
  return (d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d).astimezone(timezone.utc)
 except (TypeError,ValueError):return None

def number(x):
 try:
  v=float(x);return v if math.isfinite(v) else None
 except (TypeError,ValueError):return None

def rows(p):
 if not p.exists():return []
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def save(p,entries,fields):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp')
 with tmp.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(entries)
 os.replace(tmp,p)

def roster(root,div,now,max_age_days):
 folder=root/'data'/'roster_experiment_v105'
 label=f'{div}-college-basketball'
 csvfile=folder/(label+'_experimental_roster_sensitivity.csv')
 summ=folder/'summary.json'
 if not csvfile.exists() or not summ.exists():return None,'V105 roster data/summary unavailable'
 try:meta=json.loads(summ.read_text())
 except Exception:return None,'V105 summary unreadable'
 created=utc(meta.get('generated_at_utc'))
 if created is None or not timedelta(0)<=now-created<=timedelta(days=max_age_days):return None,'V105 snapshot time missing, future, or stale'
 data=rows(csvfile)
 if not data:return None,'V105 CSV empty'
 out={};unusable=0
 for r in data:
  tid=str(r.get('team_id') or '').strip()
  if not tid or tid in out:return None,'Duplicate or missing V105 team ID'
  # V105's actual field is illustrative_adjustment; reject unintended schemas.
  val=number(r.get('illustrative_adjustment_points'))
  available=str(r.get('data_available','')).strip().lower()
  if available in ('false','0','no') or val is None:
   out[tid]=None;unusable+=1
  else:out[tid]=val
 return {'adjustments':out,'created':created,'sha':hashlib.sha256(csvfile.read_bytes()).hexdigest(),'unusable':unusable},None

def build(forecasts,previous,rosters,now,season,min_lead=30,max_age_minutes=20):
 locked={(r['division'],r['game_id']) for r in previous}
 created=[];skipped=defaultdict(int)
 for f in forecasts:
  div=f.get('division','');key=(div,f.get('game_id',''))
  if div not in DIVS or not key[1] or f.get('model_id')!='official_saved_v97' or key in locked:continue
  tip=utc(f.get('game_start_utc'));ft=utc(f.get('forecast_created_utc'));asof=utc(f.get('ratings_snapshot_utc'))
  rs=rosters.get(div)
  if rs is None:skipped['no_roster_snapshot']+=1;continue
  if not tip or not ft or not asof or not (asof<=ft<=now<tip-timedelta(minutes=min_lead)):
   skipped['invalid_or_late_forecast']+=1;continue
  # Pair only freshly made official forecasts; never retroactively apply V105 changes.
  if now-ft>timedelta(minutes=max_age_minutes) or rs['created']>ft:
   skipped['not_contemporaneous_or_roster_postdates_forecast']+=1;continue
  h,a=str(f.get('home_id','')),str(f.get('away_id',''))
  ha=rs['adjustments'].get(h);aa=rs['adjustments'].get(a)
  if ha is None or aa is None:
   skipped['missing_roster_signal']+=1;continue
  baseline=number(f.get('predicted_home_margin'))
  if baseline is None or not (h and a and h!=a):skipped['invalid_baseline']+=1;continue
  experimental=baseline+ha-aa
  record={
   'season':season,'division':div,'game_id':key[1],'game_start_utc':f['game_start_utc'],
   'home_id':h,'away_id':a,'home_team':f.get('home_team',''),'away_team':f.get('away_team',''),
   'neutral':f.get('neutral',''),'baseline_model_id':'official_saved_v97',
   'baseline_forecast_created_utc':f['forecast_created_utc'],
   'paired_created_utc':now.isoformat().replace('+00:00','Z'),
   'ratings_snapshot_utc':f['ratings_snapshot_utc'],
   'baseline_snapshot_sha256':f.get('snapshot_sha256',''),
   'roster_snapshot_created_utc':rs['created'].isoformat().replace('+00:00','Z'),
   'roster_snapshot_sha256':rs['sha'],
   'baseline_predicted_home_margin':round(baseline,6),
   'home_roster_adjustment':round(ha,6),'away_roster_adjustment':round(aa,6),
   'experimental_predicted_home_margin':round(experimental,6),
   'model_id':'v109_v105_uncalibrated_roster',
   'experiment_note':'Illustrative V105 adjustments; NOT fitted/validated; no official predictions changed'}
  created.append(record);locked.add(key)
 return created,dict(skipped)

def evaluate(pairs,results,min_lead):
 lookup={(r.get('division'),r.get('game_id')):r for r in results if r.get('status')=='Final'}
 out=[]
 for p in pairs:
  tip=utc(p.get('game_start_utc'));created=utc(p.get('paired_created_utc'));base_created=utc(p.get('baseline_forecast_created_utc'));rs_created=utc(p.get('roster_snapshot_created_utc'))
  if not all((tip,created,base_created,rs_created)) or not (rs_created<=base_created<=created<=tip-timedelta(minutes=min_lead)):continue
  r=lookup.get((p['division'],p['game_id']))
  if not r:continue
  actual=number(r.get('actual_home_margin'))
  b=number(p.get('baseline_predicted_home_margin'));e=number(p.get('experimental_predicted_home_margin'))
  if None in (actual,b,e):continue
  out.append({'division':p['division'],'game_id':p['game_id'],'actual':actual,'baseline':b,'experimental':e})
 result={}
 for div in DIVS:
  d=[r for r in out if r['division']==div];n=len(d)
  if not n:result[div]={'paired_completed_games':0,'status':'INSUFFICIENT_PROSPECTIVE_DATA'};continue
  mae=lambda k:sum(abs(r[k]-r['actual']) for r in d)/n
  acc=lambda k: (sum((r[k]>0)==(r['actual']>0) for r in d if r[k]!=0 and r['actual']!=0),sum(r[k]!=0 and r['actual']!=0 for r in d))
  wb,nb=acc('baseline');we,ne=acc('experimental')
  b,e=mae('baseline'),mae('experimental')
  result[div]={'paired_completed_games':n,'baseline_margin_mae':round(b,4),'experimental_margin_mae':round(e,4),
   'mae_improvement_positive_is_better':round(b-e,4),'baseline_winner_accuracy':round(wb/nb,4) if nb else None,
   'experimental_winner_accuracy':round(we/ne,4) if ne else None,'baseline_winner_n':nb,'experimental_winner_n':ne,
   'status':'DESCRIPTIVE_ONLY_NOT_CAUSAL_OR_VALIDATED'}
 return result

def run(root,season,now,min_lead,max_roster_days):
 folder=root/'data'/'prospective'/season
 ff=folder/'forecasts.csv';rr=folder/'results.csv';pf=folder/'roster_pairs_v109.csv';sf=folder/'roster_evaluation_v109.json'
 forecasts=rows(ff);prior=rows(pf);results=rows(rr)
 if pf.exists() and not set(FIELDS).issubset(set(prior[0].keys()) if prior else set(next(csv.reader(pf.open()),[]))):raise ValueError('Unexpected existing pair journal schema')
 rosters={};errors={}
 for div in DIVS:
  data,err=roster(root,div,now,max_roster_days)
  if err:errors[div]=err
  else:rosters[div]=data
 added,skipped=build(forecasts,prior,rosters,now,season,min_lead)
 pairs=prior+added
 # Immutable existing rows: only append new distinct game pairs.
 if added or not pf.exists():save(pf,pairs,FIELDS)
 summary={'version':109,'season':season,'generated_at_utc':now.isoformat().replace('+00:00','Z'),
  'status':'PROSPECTIVE_PAIRED_RESEARCH_ONLY','production_modified':False,
  'baseline_source':'V97 official_saved_v97 pregame forecast archive',
  'experimental_source':'V105 static illustrative adjustments locked at first V109 pairing',
  'limitations':['Only fresh official V97 forecasts are eligible; no historical backfill','Only games with documented V105 signals for both teams are paired','V105 is uncalibrated and not opponent-strength normalized','Frozen pregame source timestamps do not establish absence of training leakage upstream','No Brier score or win probabilities'],
  'roster_errors':errors,'skipped_new_pairs':skipped,'new_pairs':len(added),'total_pairs':len(pairs),
  'paired_results':evaluate(pairs,results,min_lead)}
 sf.parent.mkdir(parents=True,exist_ok=True);sf.write_text(json.dumps(summary,indent=2)+'\n')
 return summary

def main():
 a=argparse.ArgumentParser();a.add_argument('--root',type=Path,default=Path('.'));a.add_argument('--season',default='2026-27');a.add_argument('--minimum-lead-minutes',type=int,default=30);a.add_argument('--max-roster-age-days',type=int,default=240)
 args=a.parse_args()
 if args.minimum_lead_minutes<30:raise ValueError('Minimum lead must be >= 30')
 result=run(args.root,args.season,datetime.now(timezone.utc),args.minimum_lead_minutes,args.max_roster_age_days)
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""V110 read-only diagnostics for V97 -> V109 prospective collection."""
import argparse,csv,json,math
from pathlib import Path
from datetime import datetime,timezone,timedelta
from collections import Counter

SPORTS={'mens':'mens-college-basketball','womens':'womens-college-basketball'}

def dt(x):
 try:
  t=datetime.fromisoformat(str(x).replace('Z','+00:00'));return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)
 except (ValueError,TypeError):return None

def readcsv(p):
 if not p.exists():return [],'missing'
 try:
  with p.open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f)),None
 except Exception as e:return [],str(e)

def readjson(p):
 if not p.exists():return {},'missing'
 try:return json.loads(p.read_text()),None
 except Exception as e:return {},str(e)

def classify_forecast(f,now,roster):
 tip=dt(f.get('game_start_utc'));created=dt(f.get('forecast_created_utc'));asof=dt(f.get('ratings_snapshot_utc'))
 if f.get('model_id')!='official_saved_v97':return 'not_official_model'
 if not tip or not created or not asof or not(asof<=created<=now<tip-timedelta(minutes=30)):return 'invalid_or_late_timestamps'
 if now-created>timedelta(minutes=20):return 'older_than_v109_20_minute_window'
 if roster.get('error'):return 'roster_unavailable'
 if roster['created']>created:return 'roster_newer_than_forecast'
 h,a=f.get('home_id',''),f.get('away_id','')
 if roster['adjustments'].get(str(h)) is None or roster['adjustments'].get(str(a)) is None:return 'missing_roster_signal'
 try:
  if not math.isfinite(float(f.get('predicted_home_margin',''))):return 'invalid_margin'
 except (ValueError,TypeError):return 'invalid_margin'
 return 'pairable_now_if_not_previously_locked'

def diagnose(root,season,now):
 folder=root/'data'/'prospective'/season
 forecasts,ferr=readcsv(folder/'forecasts.csv');pairs,perr=readcsv(folder/'roster_pairs_v109.csv');results,rerr=readcsv(folder/'results.csv')
 v97,e97=readjson(folder/'summary.json');v109,e109=readjson(folder/'roster_evaluation_v109.json')
 v105,e105=readjson(root/'data'/'roster_experiment_v105'/'summary.json')
 output={'version':110,'as_of_utc':now.isoformat().replace('+00:00','Z'),'season':season,'status':'READ_ONLY_DIAGNOSTIC','production_modified':False,'input_status':{'v97_summary':e97 or 'found','v109_summary':e109 or 'found','v105_summary':e105 or 'found','v97_forecasts':ferr or 'found','v97_results':rerr or 'found','v109_pairs':perr or 'found'},'v97_reported_today':v97.get('today',{}),'v109_reported_skips':v109.get('skipped_new_pairs',{}),'divisions':{},'conclusions':[]}
 created=dt(v105.get('generated_at_utc'));fresh=created and timedelta(0)<=now-created<=timedelta(days=240)
 locked={(x.get('division'),x.get('game_id')) for x in pairs}
 for div,sport in SPORTS.items():
  v=forecasts and [f for f in forecasts if f.get('division')==div] or []
  off=[f for f in v if f.get('model_id')=='official_saved_v97']
  roster_rows,rerr=readcsv(root/'data'/'roster_experiment_v105'/(sport+'_experimental_roster_sensitivity.csv'))
  roster={'error':None,'created':created,'adjustments':{}}
  if rerr or not fresh or not roster_rows:
   roster['error']=('missing or invalid roster CSV' if rerr or not roster_rows else 'V105 timestamp missing/future/stale')
  else:
   for r in roster_rows:
    tid=str(r.get('team_id') or '').strip();val=r.get('illustrative_adjustment_points')
    try:adj=float(val);adj=adj if math.isfinite(adj) and str(r.get('data_available','')).lower() not in ('false','0','no') else None
    except (ValueError,TypeError):adj=None
    if tid:roster['adjustments'][tid]=adj
  ratingstatus,sterr=readjson(root/'data'/'ratings'/sport/'status.json');updated=dt(ratingstatus.get('updated_utc'))
  snapshot=root/'data'/'ratings'/sport/'latest.csv.gz'
  rating_age=(now-updated).total_seconds()/3600 if updated else None
  remaining=[f for f in off if (div,f.get('game_id')) not in locked]
  reasons=Counter(classify_forecast(f,now,roster) for f in remaining)
  future=[f for f in off if (t:=dt(f.get('game_start_utc'))) and t>now]
  upcoming42=[f for f in future if dt(f['game_start_utc'])<=now+timedelta(hours=42)]
  future.sort(key=lambda f:f.get('game_start_utc',''))
  info={'v97_total_forecasts':len(v),'v97_official_forecasts':len(off),'v97_unpaired_official_forecasts':len(remaining),'v109_locked_pairs':sum(r.get('division')==div for r in pairs),'v97_final_results':sum(r.get('division')==div for r in results),'v97_future_official_forecasts':len(future),'v97_future_forecasts_within_42h':len(upcoming42),'next_saved_forecast_game_start_utc':future[0].get('game_start_utc') if future else None,'ratings_snapshot_exists':snapshot.exists(),'ratings_updated_utc':ratingstatus.get('updated_utc'),'ratings_age_hours':round(rating_age,2) if rating_age is not None else None,'ratings_fresh_48h':rating_age is not None and 0<=rating_age<=48,'v105_roster_status':roster['error'] or 'available','v105_roster_team_count':len(roster['adjustments']),'v109_unpaired_forecast_reasons':dict(reasons),'v97_last_run_info':v97.get('today',{}).get(div,{})}
  output['divisions'][div]=info
  if len(off)==0:
   output['conclusions'].append(f'{div}: no official V97 forecasts saved. Inspect V97 summary games_seen, forecasts_created and official_ratings; V97 only forecasts games within 42h of tipoff.')
  if info['v97_last_run_info'].get('official_ratings') not in ('available',None):output['conclusions'].append(f"{div}: V97 reported unavailable official ratings: {info['v97_last_run_info']['official_ratings']}")
  if info['v97_last_run_info'].get('games_seen')==0:output['conclusions'].append(f'{div}: latest V97 run saw zero games in its ESPN five-day scoreboard window.')
  if not info['ratings_fresh_48h']:output['conclusions'].append(f'{div}: current ratings do not pass V97 48h freshness check (or metadata unavailable).')
  if roster['error']:output['conclusions'].append(f"{div}: V105 unavailable to pair: {roster['error']}")
  if reasons:output['conclusions'].append(f'{div}: V109 eligibility diagnostics on unpaired archived forecasts: {dict(reasons)}')
 if not forecasts:output['conclusions'].append('No saved forecast records. The diagnostic cannot establish whether games exist upstream; check V97 output in GitHub Actions.')
 return output

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path('.'));ap.add_argument('--season',default='2026-27');a=ap.parse_args()
 result=diagnose(a.root,a.season,datetime.now(timezone.utc));target=a.root/'data'/'prospective'/a.season/'diagnostics_v110.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

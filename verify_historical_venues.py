"""Fetch verified ESPN neutral-site flags for dates in a paired historic archive.
Never infers non-neutral from missing metadata. No modification of source archive.
"""
import argparse
import json
import time
from pathlib import Path
import pandas as pd
import requests

SPORTS={'mens':'mens-college-basketball','womens':'womens-college-basketball'}

def build(games, division, output, existing=None, session=None):
    g=pd.read_csv(games,dtype={'game_id':str,'home_id':str,'away_id':str})
    if g.empty: raise ValueError('No games in input archive')
    if g.game_id.duplicated().any():raise ValueError('Duplicate game IDs in archive')
    g['date']=pd.to_datetime(g.date,utc=True,errors='raise')
    dates=sorted(g.date.dt.strftime('%Y%m%d').unique())
    old={}
    if existing and Path(existing).exists():
        prev=pd.read_csv(existing,dtype={'game_id':str,'home_id':str,'away_id':str})
        if 'neutral_verified' in prev:
            old={str(r.game_id):r for r in prev.itertuples(index=False) if str(r.neutral_verified).lower()=='true'}
        # Note: prior verified false rows must also be preserved.
        for r in prev.itertuples(index=False):
            if str(getattr(r,'neutral_verified','')).lower() in ('true','false'):old[str(r.game_id)]=r
    s=session or requests.Session()
    s.headers.update({'User-Agent':'CourtsideAnalytics/1.0 research', 'Accept':'application/json'})
    found={}; failed=[]; checked=0
    for date in dates:
        subset=g[g.date.dt.strftime('%Y%m%d')==date]
        if all(str(id) in old for id in subset.game_id):continue
        url=f'https://site.api.espn.com/apis/site/v2/sports/basketball/{SPORTS[division]}/scoreboard'
        doc=None
        for retry in range(3):
            try:
                resp=s.get(url,params={'dates':date,'groups':'50','limit':500},timeout=35)
                resp.raise_for_status();doc=resp.json()
                if not isinstance(doc.get('events'),list) or len(doc['events'])>=500:raise ValueError('Scoreboard missing or truncated')
                break
            except (requests.RequestException,ValueError):
                if retry<2:time.sleep(retry+1)
        if doc is None:
            failed.append(date);continue
        checked+=1
        for e in doc['events']:
            comp=(e.get('competitions') or [None])[0]
            if comp is None or not isinstance(comp.get('neutralSite'),bool):continue
            competitors=comp.get('competitors') or []
            h=next((str(z.get('team',{}).get('id')) for z in competitors if z.get('homeAway')=='home'),None)
            a=next((str(z.get('team',{}).get('id')) for z in competitors if z.get('homeAway')=='away'),None)
            found[str(e.get('id'))]={'home_id':h,'away_id':a,'neutral_site':comp['neutralSite']}
    out=[]; missing=[]; conflicts=[]
    for x in g.itertuples(index=False):
        gid=str(x.game_id)
        v=found.get(gid)
        if v is not None and (v['home_id']!=str(x.home_id) or v['away_id']!=str(x.away_id)):
            conflicts.append(gid);v=None
        if v is None and gid in old:
            prior=old[gid]
            if str(prior.home_id)==str(x.home_id) and str(prior.away_id)==str(x.away_id):
                is_neutral=str(prior.neutral_site).lower()=='true'
                v={'neutral_site':is_neutral}
        if v is None:missing.append(gid)
        out.append({'game_id':gid,'home_id':str(x.home_id),'away_id':str(x.away_id),
                    'neutral_site':v['neutral_site'] if v else '', 'neutral_verified':bool(v is not None)})
    if conflicts:raise ValueError(f'Conflicting ESPN teams for {len(conflicts)} IDs: {conflicts[:5]}')
    p=Path(output);p.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(out).to_csv(p,index=False)
    report={'division':division,'games':len(g),'verified':len(g)-len(missing),'unverified':len(missing),
            'verified_fraction':round((len(g)-len(missing))/len(g),4),'scoreboard_dates_fetched':checked,
            'failed_dates':failed,'unverified_sample':missing[:10]}
    p.with_suffix('.summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--games',required=True)
    parser.add_argument('--division',required=True,choices=SPORTS)
    parser.add_argument('--out',required=True);parser.add_argument('--existing')
    a=parser.parse_args(); build(a.games,a.division,a.out,a.existing)
if __name__=='__main__':main()

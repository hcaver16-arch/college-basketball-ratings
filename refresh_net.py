"""Guarded scheduled importer of NCAA NET rankings as republished by WarrenNolan.

Run after the NCAA begins publishing current-season NET. Failed or incomplete runs
never overwrite the most recent validated snapshot. No modeled rankings are used.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import re
import unicodedata
import requests
from bs4 import BeautifulSoup

SEASON = '2026-27'
END_YEAR = 2027
SOURCES = {'mens': ('basketball', 'mens-college-basketball'), 'womens': ('basketballw', 'womens-college-basketball')}
BASE = 'https://www.warrennolan.com'
ESPN = 'https://site.api.espn.com/apis/site/v2/sports/basketball'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; CourtsideNETMonitor/1.0)', 'Accept': 'text/html,application/json'}

# Match only known institution naming alternatives, not nickname-based guesses.
ALIASES = {
    'uconn': 'connecticut', 'unc': 'north carolina', 'nc state': 'north carolina state',
    'ole miss': 'mississippi', 'byu': 'brigham young', 'smu': 'southern methodist',
    'ucf': 'central florida', 'uncw': 'unc wilmington', 'utsa': 'texas san antonio',
    'utep': 'texas el paso', 'lsu': 'louisiana state', 'usc': 'southern california',
    'miami fl': 'miami', 'miami florida': 'miami', 'miami oh': 'miami ohio',
    'saint johns': 'st johns', 'saint marys college': 'saint marys',
    'saint louis': 'st louis', 'saint peters': 'st peters',
    'saint bonaventure': 'st bonaventure', 'california baptist': 'cal baptist',
    'mcneese': 'mcneese state', 'sam houston state': 'sam houston',
    'stephen f austin': 'stephen f austin', 'st thomas': 'saint thomas',
}

def normalize(name):
    name = unicodedata.normalize('NFKD', str(name)).encode('ascii','ignore').decode('ascii').lower()
    name = re.sub(r'&', ' and ', name)
    name = re.sub(r'[^a-z0-9 ]', ' ', name)
    name = re.sub(r'\b(university|college)\b', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return ALIASES.get(name, name)

def get_directory(session, sport):
    r=session.get(f'{ESPN}/{sport}/teams',params={'limit':1000,'groups':'50'},headers=HEADERS,timeout=35)
    r.raise_for_status()
    payload=r.json()
    league=(payload.get('sports') or [{}])[0].get('leagues') or []
    entries=[t for block in league for t in (block.get('teams') or [])]
    if not entries: entries=payload.get('teams') or []
    result={}
    duplicates=set()
    for obj in entries:
        t=obj.get('team',obj)
        tid=str(t.get('id','')).strip()
        for nm in [t.get('displayName'),t.get('shortDisplayName'),t.get('name'),t.get('location')]:
            if not nm or not tid: continue
            key=normalize(nm)
            if key in result and result[key]!=tid: duplicates.add(key)
            else: result[key]=tid
    for key in duplicates: result.pop(key,None)
    if len(set(result.values()))<300: raise ValueError('ESPN D1 directory coverage is too small')
    return result

def fetch_net_page(session, kind):
    url=f'{BASE}/{SOURCES[kind][0]}/{END_YEAR}/net'
    r=session.get(url,headers=HEADERS,timeout=40)
    r.raise_for_status()
    soup=BeautifulSoup(r.text,'html.parser')
    text=soup.get_text(' ',strip=True)
    if not re.search(r'NET Rankings',text,re.I):
        raise ValueError('Not an identifiable NET rankings page')
    if not re.search(r'NET Rank updated|NET Rank.*games through',text,re.I):
        raise ValueError('NET publication/update marker missing (likely preseason placeholder)')
    tables=soup.find_all('table')
    parsed=[]
    for table in tables:
        header=' '.join(cell.get_text(' ',strip=True) for cell in table.find_all('th'))
        if 'NET' not in header.upper(): continue
        rows=[]
        for tr in table.find_all('tr'):
            cells=tr.find_all(['td'],recursive=False)
            if len(cells)<3: continue
            name=cells[0].get_text(' ',strip=True)
            match=re.search(r'^\s*(\d+)\s*$',cells[2].get_text(' ',strip=True))
            if not match or not name: continue
            rows.append((name,int(match.group(1))))
        if len(rows)>len(parsed): parsed=rows
    if len(parsed)<300:
        raise ValueError(f'NET listing incomplete or layout changed: {len(parsed)} parsed ranks')
    ranks=[rank for _,rank in parsed]
    if len(set(ranks))!=len(ranks) or min(ranks)!=1 or max(ranks)>len(ranks)+3:
        raise ValueError('Invalid, duplicate or nonsequential NET ranks')
    return url,parsed

def import_kind(kind, root, session=None, timestamp=None):
    session=session or requests.Session()
    timestamp=timestamp or datetime.now(timezone.utc)
    if timestamp.month < 12 and timestamp.year == END_YEAR-1:
        return 'preseason — NET not yet published; no data written'
    url, listing=fetch_net_page(session,kind)
    directory=get_directory(session,SOURCES[kind][1])
    matched=[]; unmatched=[]; used=set()
    for name, rank in listing:
        tid=directory.get(normalize(name))
        if not tid or tid in used:
            unmatched.append(name)
        else:
            matched.append((tid,rank,name));used.add(tid)
    # Do not publish incomplete or mismapped results as official quadrants.
    if len(matched)<300 or len(matched)/len(listing)<0.85:
        raise ValueError(f'Only {len(matched)}/{len(listing)} NET teams matched unambiguously to ESPN IDs; nothing saved. Unmatched examples: {unmatched[:12]}')
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    stamp=timestamp.date().isoformat()
    target=root/f'{kind}_net.csv'
    history=root/f'{kind}_snapshots'/f'{stamp}.csv'
    if history.exists(): return f'{kind}: same-day validated snapshot already archived ({len(matched)} teams)'
    rows=[{'team_id':tid,'net_rank':rank,'snapshot_date':stamp,'season':SEASON,'source':f'NCAA NET republished by Warren Nolan — {url}'} for tid,rank,_ in matched]
    fieldnames=['team_id','net_rank','snapshot_date','season','source']
    history.parent.mkdir(parents=True,exist_ok=True)
    def save(path):
        tmp=path.with_suffix('.csv.tmp')
        with tmp.open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=fieldnames);writer.writeheader();writer.writerows(rows)
        tmp.replace(path)
    save(history);save(target)
    (root/f'{kind}_match_report.txt').write_text(f'Source: {url}\nRetrieved UTC: {timestamp.isoformat()}\nMatched: {len(matched)} of {len(listing)}\nUnmatched: {unmatched}\n',encoding='utf8')
    return f'{kind}: saved {len(matched)} matched NET ranks; {len(unmatched)} unmatched'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',default='data/net');args=ap.parse_args()
    errors=[]
    for kind in SOURCES:
        try: print(import_kind(kind,args.root))
        except Exception as exc:
            print(f'{kind}: NET update skipped: {exc}')
            errors.append(kind)
    # Never damage the existing snapshots; failure can be diagnosed in Actions.
    if errors: raise SystemExit('No overwrite for failed divisions: '+','.join(errors))

if __name__=='__main__': main()

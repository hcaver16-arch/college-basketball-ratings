#!/usr/bin/env python3
"""V204 school-site roster collection and research-only source reconciliation.

Known, explicitly curated official school URLs only. No search-result guessing,
no ESPN player list mislabeled as independent verification, no fuzzy identity
joins and no automatic model adjustment. Failed pages remain unverified.
"""
from __future__ import annotations
import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from archive_roster_batch import directory as espn_directory
from priority_schedule import upcoming_d1_ids
from official_roster_reconcile_v202 import normalized_name, reconcile
from independent_roster_prospective_v203 import candidates, truth

SPORT = "mens-college-basketball"
ROOT = Path(__file__).resolve().parent
FOLDER = Path("data/official_roster_evidence_v204")
MANIFEST = ROOT / FOLDER / "source_manifest.csv"
MIN_PLAYERS = 8
MAX_PLAYERS = 22
MIN_MATCHED_ESPN = 4
HEADERS = {"User-Agent":"Mozilla/5.0 CourtsideResearchRosterCollector/1.0","Accept":"text/html,application/xhtml+xml"}
SELECTORS = (
    ".sidearm-roster-player-name",
    "[class*='roster-player-name']",
    "[class*='roster_player_name']",
    "[class*='roster-players__name']",
    "[class*='roster__player-name']",
    "[class*='rosterPlayerName']",
    "[class*='s-person-card__name']",
    "[data-testid='roster-player-name']",
    "[data-roster-name]",
)

def season_match(title, year):
    t = re.sub(r"\s+"," ",str(title).lower())
    variants = {"2025-26","2025–26","2025-2026","2025–2026"} if year==2026 else {
        "2026-27","2026–27","2026-2027","2026–2027"
    }
    return "basketball" in t and "roster" in t and any(v in t for v in variants)


def clean_player(text):
    value = re.sub(r"\s+"," ",str(text)).strip()
    value = re.sub(r"(?i)^full bio(?: for)?\s+","",value)
    value = re.sub(r"(?i)\s+full bio$","",value).strip()
    # Avoid accidental inclusion of classes, player positions, jersey numbers,
    # biographies, navigation, team titles, and staff.
    if not (3<=len(value)<=65) or any(c.isdigit() for c in value):
        return ""
    if len(normalized_name(value).split())<2 or len(value.split())>6:
        return ""
    if any(word in value.lower() for word in ("roster","assistant coach","head coach","graduate assistant",
        "staff", "athletics", "download", "full name","basketball","university","more info","view profile")):
        return ""
    return value

def _from_table(soup):
    """Only tables with an explicit Name/Full Name player heading."""
    names = []
    for table in soup.select("table"):
        header=table.find("thead")
        if header is None:continue
        heads=[x.get_text(" ",strip=True).lower() for x in header.select("th")]
        name_cols=[i for i,col in enumerate(heads) if col in ("name","full name","player","student-athlete")]
        if not name_cols:continue
        idx=name_cols[0]
        for row in table.select("tbody tr"):
            cells=row.find_all(["td","th"],recursive=False)
            if idx>=len(cells):continue
            name=clean_player(cells[idx].get_text(" ",strip=True))
            if name:names.append(name)
        if len(names)>=MIN_PLAYERS:break
    return names

def extract_roster_players(html,year):
    soup=BeautifulSoup(html,"html.parser")
    title=soup.title.get_text(" ",strip=True) if soup.title else ""
    headings=" ".join(x.get_text(" ",strip=True) for x in soup.find_all(["h1","h2"],limit=7))
    if not season_match(title+" "+headings,year):
        return [],"roster_season_not_confirmed_by_page_heading"
    names=[]
    for sel in SELECTORS:
        parts=soup.select(sel)
        for part in parts:
            if part.find_parent(["nav","footer"]):continue
            name=clean_player(part.get_text(" ",strip=True))
            if name:names.append(name)
        if len(names)>=MIN_PLAYERS:break
    if len(names)<MIN_PLAYERS:
        names=_from_table(soup)
    if len(names)<MIN_PLAYERS:
        # Only detail-page links whose href has an athlete slug and final ID.
        for a in soup.select('a[href*="/roster/"]'):
            href=a.get("href","")
            if not re.search(r"/roster/[^/?#]+/\d{3,}(?:[/?#]|$)",href):continue
            if a.find_parent(["nav","footer"]):continue
            name=clean_player(a.get_text(" ",strip=True))
            if name:names.append(name)
    if len(names)<MIN_PLAYERS:
        # Some school templates use athlete-name headings rather than SIDEARM
        # classes. Stop before the coaching-staff section and still require
        # a plausible cohort plus exact ESPN identity corroboration downstream.
        heading_names=[]
        for header in soup.find_all(["h2","h3","h4"]):
            raw=header.get_text(" ",strip=True)
            if "coaching staff" in raw.casefold():
                break
            if header.name not in ("h3","h4"):
                continue
            candidate=clean_player(raw)
            if candidate:heading_names.append(candidate)
        if len(heading_names)>=MIN_PLAYERS:
            names=heading_names
    if not names:return [],"no_structured_player_names"
    seen={}
    for name in names:
        key=normalized_name(name)
        if not key:continue
        if key in seen and seen[key]!=name:
            return [],"ambiguous_duplicate_normalized_player_name"
        seen[key]=name
    if not MIN_PLAYERS<=len(seen)<=MAX_PLAYERS:
        return [],f"implausible_roster_size_{len(seen)}"
    return list(seen.values()),None

def safe_url(url):
    parsed=urlparse(str(url).strip())
    host=(parsed.hostname or "").lower()
    return parsed.scheme=="https" and bool(host) and host not in ("localhost","127.0.0.1") and not host.replace(".","").isdigit() and (
        host.endswith(".com") or host.endswith(".edu")
    ) and parsed.username is None and parsed.password is None

def fetch_official(url,year,get=requests.get):
    if not safe_url(url):return [],"url_not_safe_https_official_host"
    try:
        resp=get(url,headers=HEADERS,timeout=20)
        resp.raise_for_status()
        final=str(getattr(resp,"url",url))
        initial_host=(urlparse(url).hostname or "").removeprefix("www.")
        final_host=(urlparse(final).hostname or "").removeprefix("www.")
        if not safe_url(final) or initial_host!=final_host:
            return [],"unexpected_cross_host_redirect"
        if "text/html" not in str(resp.headers.get("content-type","text/html")).lower():
            return [],"not_html"
        if len(resp.content)>3_000_000:return [],"page_too_large"
        return extract_roster_players(resp.text,year)
    except (requests.RequestException,ValueError,TypeError) as exc:
        return [],"source_request_failed_"+type(exc).__name__

def choose_targets(manifest,directory,priority_ids,limit):
    """Exact ESPN directory identity only, upcoming opponents first."""
    known=directory[["Team ID","Team"]].drop_duplicates("Team ID")
    indexed={}
    for r in known.to_dict("records"):
        key=normalized_name(r["Team"])
        indexed.setdefault(key,[]).append(str(r["Team ID"]))
    entries=[]
    for r in manifest.to_dict("records"):
        ids=indexed.get(normalized_name(r["ESPN Team"]),[])
        d=dict(r)
        d["Team ID"]=ids[0] if len(ids)==1 else ""
        d["Directory status"]="exact_d1_match" if len(ids)==1 else "not_unique_or_missing_in_espn_directory"
        entries.append(d)
    entries.sort(key=lambda r:(0 if r["Team ID"] in priority_ids else 1, r["ESPN Team"]))
    return entries[:limit]

def row_records(team,season,names,url,checked_at):
    return [{"Team ID":str(team["Team ID"]),"Team":team["ESPN Team"],"Season":season,
        "Player":n,"Source URL":url,"Checked UTC":checked_at,
        "Source type":"Verified season-labeled official athletics roster page"}
        for n in names]

def _subset(df,team_id):
    if not isinstance(df,pd.DataFrame) or df.empty:return pd.DataFrame()
    return df.loc[df["Team ID"].astype(str).eq(str(team_id))].copy()

def perform(sources, fetcher=None, now=None):
    """Fetch both seasons per team; if one fails do not upgrade that team."""
    fetcher = fetcher or fetch_official
    now=now or datetime.now(timezone.utc)
    checked=now.isoformat()
    audit=[];previous=[];current=[]
    def one(item):
        r=item.copy(); tid=str(r.get("Team ID") or "")
        info={"team":r["ESPN Team"],"team_id":tid,
              "directory_status":r["Directory status"],
              "priority_upcoming":bool(r.get("Priority upcoming",False)),
              "prior_official_url":r["Prior official URL"],
              "current_official_url":r["Current official URL"],"checked_utc":checked}
        if not tid:
            info.update(status="unverified_directory_identity",prior_players=0,current_players=0)
            return info,[],[]
        earlier,err1=fetcher(r["Prior official URL"],2026)
        newer,err2=fetcher(r["Current official URL"],2027)
        info.update(prior_players=len(earlier),current_players=len(newer),
                    prior_issue=err1,current_issue=err2)
        # Never turn a missing roster response into a partial player pool.
        if err1 or err2:
            info["status"]="needs_manual_source_review"
            return info,[],[]
        info["status"]="official_pages_parsed"
        return info,row_records(r,"2025-26",earlier,r["Prior official URL"],checked),row_records(r,"2026-27",newer,r["Current official URL"],checked)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(one,item) for item in sources]
        for future in as_completed(futures):
            info,old,new=future.result()
            audit.append(info);previous.extend(old);current.extend(new)
    return sorted(audit,key=lambda d:d["team"]),previous,current

def _ensure_rows(rows):
    return pd.DataFrame(rows,columns=["Team ID","Team","Season","Player","Source URL","Checked UTC","Source type"])

def _match(official,previous,current,stats):
    if official.empty:return pd.DataFrame()
    frames=[]
    for tid,school in official.groupby("Team ID"):
        try: frames.append(reconcile(school,previous,current,stats))
        except ValueError: continue
    return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()

def _fallback(records,base,excluded):
    """Carry forward V202 source-backed records for skipped teams, with original checked dates."""
    if not base.is_file():return records
    frame=pd.read_csv(base,dtype={"Team ID":str},keep_default_na=False)
    if not {"Team ID","Team","Season","Player","Source URL","Checked UTC","Source type"}.issubset(frame.columns):
        return records
    frame=frame[~frame["Team ID"].isin(excluded)]
    if frame.empty:return records
    return pd.concat([records,frame],ignore_index=True)

def _fallback_links(links,path,excluded):
    if not path.is_file():return links
    backup=pd.read_csv(path,dtype={"Team ID":str,"ESPN Player ID":str},keep_default_na=False)
    backup=backup[~backup["Team ID"].isin(excluded)]
    if backup.empty:return links
    if links.empty:return backup
    return pd.concat([links,backup],ignore_index=True)

def run(root=ROOT,limit=26,now=None,remote=True):
    now=now or datetime.now(timezone.utc)
    folder=root/FOLDER; folder.mkdir(parents=True,exist_ok=True)
    manifest=pd.read_csv(root/FOLDER/"source_manifest.csv",dtype=str,keep_default_na=False)
    if manifest["ESPN Team"].duplicated().any():raise ValueError("Duplicate official school identity in manifest")
    if not manifest["Prior official URL"].map(safe_url).all() or not manifest["Current official URL"].map(safe_url).all():
        raise ValueError("Manifest has invalid non-HTTPS source URLs")
    known=espn_directory(SPORT) if remote else pd.DataFrame(columns=["Team ID","Team"])
    priority_ids,priority_errors=upcoming_d1_ids(SPORT,set(known["Team ID"].astype(str)),days=14) if remote else (set(),[])
    selected=choose_targets(manifest,known,priority_ids,limit)
    for item in selected:item["Priority upcoming"]=item["Team ID"] in priority_ids
    audit,old_rows,new_rows=perform(selected,now=now)
    old=_ensure_rows(old_rows);current=_ensure_rows(new_rows)
    # A structured roster page is necessary but not sufficient: insist that
    # both seasons independently corroborate multiple unique ESPN athletes.
    def archive(kind):
        path=root/"data"/f"{SPORT}_{kind}.csv.gz"
        return pd.read_csv(path,dtype={"Team ID":str,"Player ID":str}) if path.is_file() else pd.DataFrame()
    prev_rosters=archive("previous_rosters")
    curr_rosters=archive("current_rosters")
    stats=archive("previous_stats")
    verified_ids=set()
    fresh_old_links=[]
    fresh_current_links=[]
    for tid in sorted(set(old["Team ID"].astype(str)) & set(current["Team ID"].astype(str))):
        o=_match(_subset(old,tid),prev_rosters,curr_rosters,stats)
        c=_match(_subset(current,tid),prev_rosters,curr_rosters,stats)
        past_count=int(o["Matched ESPN prior box scores"].map(truth).sum()) if not o.empty else 0
        present_count=int(c["Matched ESPN current roster"].map(truth).sum()) if not c.empty else 0
        if past_count>=MIN_MATCHED_ESPN and present_count>=MIN_MATCHED_ESPN:
            verified_ids.add(tid)
            fresh_old_links.append(o)
            fresh_current_links.append(c)
        else:
            for rec in audit:
                if rec["team_id"]==tid:
                    rec["status"]="parsed_but_insufficient_independent_id_matches"
                    rec["prior_espn_matches"]=past_count
                    rec["current_espn_matches"]=present_count
    old=old[old["Team ID"].isin(verified_ids)]
    current=current[current["Team ID"].isin(verified_ids)]
    old_links=pd.concat(fresh_old_links,ignore_index=True) if fresh_old_links else pd.DataFrame()
    curr_links=pd.concat(fresh_current_links,ignore_index=True) if fresh_current_links else pd.DataFrame()
    legacy=root/"data/official_roster_evidence_v202"
    # Backfill only when no current official source succeeded for a previously
    # reviewed team. Never forge a successful fresh fetch.
    old=_fallback(old,legacy/"mens_2025_26_school_rosters.csv",verified_ids)
    current=_fallback(current,legacy/"mens_2026_27_school_rosters.csv",verified_ids)
    # Saved V202 team-specific mapping is preserved only when its official page
    # was not replaced by a newly parsed successful source, with original checked dates.
    old_links=_fallback_links(old_links,legacy/"linked_players.csv",verified_ids)
    curr_links=_fallback_links(curr_links,legacy/"linked_current_players.csv",verified_ids)
    if old_links.empty or curr_links.empty:
        status="no_independent_both_season_coverage"
        qualifications={}
    else:
        # Reuse exactly V203's gating, not newly invented eligibility rules.
        snap={"previous":old_links,"current":curr_links,"stats":stats}
        _,qualifications=candidates(snap)
        status="research_only_not_deployed"
    for r in audit:
        q=qualifications.get(r["team_id"])
        r["qualified_v203_research"]=bool(q and q["qualified"])
        r["prior_match_pct"]=q["prior_stats_coverage_pct"] if q else None
        r["current_identity_match_pct"]=q["current_identity_coverage_pct"] if q else None
        r["blocking_reasons"]=q["blocked_reasons"] if q else ["not_reconciled"]
    old.to_csv(folder/"official_prior_rosters.csv",index=False)
    current.to_csv(folder/"official_current_rosters.csv",index=False)
    if not old_links.empty:old_links.to_csv(folder/"linked_players.csv",index=False)
    if not curr_links.empty:curr_links.to_csv(folder/"linked_current_players.csv",index=False)
    summary={
        "version":204,"checked_utc":now.isoformat(),"division":SPORT,"model_changed":False,
        "status":status,"target_count":len(selected),"manifest_count":len(manifest),
        "upcoming_target_count":sum(bool(x["Priority upcoming"]) for x in selected),
        "source_pages_parsed":sum(r["status"]=="official_pages_parsed" for r in audit),
        "both_season_independently_reconciled":len(verified_ids),
        "source_review_needed":sum(r["status"]!="official_pages_parsed" for r in audit),
        "source_schedule_errors":priority_errors,
        "qualified_team_count":sum(bool(q["qualified"]) for q in qualifications.values()),
        "qualifications":qualifications,
        "teams":audit,
        "limitations":[
            "ESPN team directory and scheduled games only choose priority; they do not prove independent school roster membership.",
            "Official school pages must show the exact season and structured player rows; otherwise they are marked unverified.",
            "ESPN player IDs, box-score game IDs and minutes stay separate from named official player listings.",
            "Reconciliation requires unique exact normalized names, not guessed transfers or fuzzy matches.",
            "Retrospective source collection cannot be applied to previous pregame forecasts.",
            "No production model changes or automatic roster adjustments; V203 must separately validate any future paired forecasts.",
        ],
    }
    (folder/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    pd.DataFrame(audit).to_csv(folder/"source_status.csv",index=False)
    print(f"V204: {len(selected)} selected, {summary['source_pages_parsed']} season-pairs parsed, "
          f"{summary['qualified_team_count']} research-eligible (including preserved V202 evidence)")
    for a in audit:
        print(f"  {a['team']}: {a['status']} prior={a['prior_players']} current={a['current_players']} "
              f"eligible={a['qualified_v203_research']} issues={a.get('prior_issue')}, {a.get('current_issue')}")
    return summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--limit",type=int,default=26,help="Number of schools (1-50), upcoming opponents prioritized")
    args=p.parse_args()
    if not 1<=args.limit<=50: p.error("--limit must be 1-50")
    run(root=args.root,limit=args.limit)

if __name__=="__main__":main()

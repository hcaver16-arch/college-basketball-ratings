"""Reconcile verified *names* on official 2025-26 school rosters with ESPN player IDs.

Output is an independent, retrospective evidence audit. Not a roster replacement,
not an automatic roster-model eligibility upgrade, and not a pregame snapshot.
Only unique exact normalized names within the same team may link to ESPN IDs.
"""
from __future__ import annotations
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from saved_roster_data import load_saved_data
from prospective_roster import evidence_adjustments

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "data/official_roster_evidence_v202/mens_2025_26_school_rosters.csv"
CURRENT_INPUT = ROOT / "data/official_roster_evidence_v202/mens_2026_27_school_rosters.csv"
OUTPUT = ROOT / "data/official_roster_evidence_v202"
SPORT = "mens-college-basketball"

def normalized_name(name):
    """Conservative exact matching: Unicode, punctuation and whitespace only."""
    if pd.isna(name):
        return ""
    txt = unicodedata.normalize("NFKD", str(name))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    txt = txt.casefold().replace("&", " and ")
    txt = re.sub(r"[^a-z0-9 ]+", " ", txt)
    tokens = txt.split()
    # C.J. / C J / CJ resolve to the same full initials, without fuzzy joins.
    if len(tokens) >= 3 and len(tokens[0]) == len(tokens[1]) == 1:
        head = 0
        while head < len(tokens) - 1 and len(tokens[head]) == 1:
            head += 1
        tokens = ["".join(tokens[:head])] + tokens[head:]
    return " ".join(tokens)

def _identity_map(frames, tid):
    """Map unambiguous team-local normalized ESPN names to player IDs and sources."""
    by_name = {}
    for label, frame in frames:
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        if not {"Team ID", "Player ID", "Player"}.issubset(frame.columns):
            continue
        sub = frame[frame["Team ID"].astype(str).eq(str(tid))]
        for item in sub.to_dict("records"):
            pid = str(item.get("Player ID") or "").strip()
            key = normalized_name(item.get("Player"))
            if not pid or pid.lower() in ("none", "nan", "<na>") or len(key.split()) < 2:
                continue
            record = by_name.setdefault(key, {"ids": set(), "sources": set()})
            record["ids"].add(pid)
            record["sources"].add(label)
    return by_name

def _ids(frame, tid):
    if not isinstance(frame,pd.DataFrame) or frame.empty or not {"Team ID","Player ID"}.issubset(frame.columns):
        return set()
    return set(frame.loc[frame["Team ID"].astype(str).eq(str(tid)), "Player ID"].dropna().astype(str))

def reconcile(official, previous, current, player_stats):
    """Return per-person evidence records without asserting missing ESPN membership."""
    required = {"Team ID", "Team", "Season", "Player", "Source URL", "Checked UTC", "Source type"}
    if not required.issubset(official.columns):
        raise ValueError("Official roster evidence missing: " + str(sorted(required-set(official.columns))))
    result = []
    # Duplicate official names are ambiguous; do not hide malformed source evidence.
    for tid, teams in official.groupby("Team ID", sort=True):
        tid=str(tid)
        matches=_identity_map((("ESPN prior roster",previous),("ESPN current roster",current),
                                ("ESPN prior box scores",player_stats)),tid)
        pid_old=_ids(previous,tid)
        pid_new=_ids(current,tid)
        pid_stats=_ids(player_stats,tid)
        keys=teams["Player"].map(normalized_name)
        if not keys.all() or keys.duplicated().any():
            raise ValueError("Official roster has empty or ambiguous duplicate names for "+tid)
        for row in teams.to_dict("records"):
            key=normalized_name(row["Player"])
            found=matches.get(key,{"ids":set(),"sources":set()})
            ids=found["ids"]
            unique=len(ids)==1
            pid=next(iter(ids)) if unique else ""
            if len(ids)>1:
                state="Ambiguous ESPN IDs — review needed"
            elif not ids:
                state="Official roster only — no exact ESPN name match"
            elif pid in pid_stats and pid in pid_old:
                state="Official + ESPN prior roster + prior box scores"
            elif pid in pid_stats:
                state="Official + ESPN prior box scores"
            elif pid in pid_old:
                state="Official + ESPN prior roster; statistics missing"
            elif pid in pid_new:
                state="Official prior + ESPN current roster only"
            else:
                state="Review ESPN name/ID provenance"
            result.append({
                "Team ID":tid,
                "Team":row["Team"],
                "Official season":row["Season"],
                "Official roster player":row["Player"],
                "ESPN Player ID":pid,
                "ESPN name sources":", ".join(sorted(found["sources"])),
                "Matched ESPN prior roster":unique and pid in pid_old,
                "Matched ESPN prior box scores":unique and pid in pid_stats,
                "Matched ESPN current roster":unique and pid in pid_new,
                "Evidence classification":state,
                "Official source URL":row["Source URL"],
                "Source checked UTC":row["Checked UTC"],
                "Evidence timing":"Retrospective verification, not historical pregame snapshot",
            })
    return pd.DataFrame(result)

def summarize(links, prev, current, stats):
    rows = []
    for tid, group in links.groupby("Team ID", sort=True):
        matched=group["Matched ESPN prior box scores"].sum()
        distinct=group["ESPN Player ID"].astype(str).ne("").sum()
        rows.append({
            "team_id":str(tid), "team":str(group.iloc[0]["Team"]),
            "official_roster_players":len(group),
            "official_names_linked_to_unique_espn_id":int(distinct),
            "official_players_linked_to_prior_stats":int(matched),
            "official_to_stats_match_pct":round(100*matched/len(group),1) if len(group) else None,
            "espn_previous_roster_player_ids":len(_ids(prev,tid)),
            "espn_prior_boxscore_player_ids":len(_ids(stats,tid)),
            "espn_current_roster_player_ids":len(_ids(current,tid)),
            "official_roster_only":int(group["ESPN Player ID"].eq("").sum()),
            "ambiguous_matches":int(group["Evidence classification"].str.startswith("Ambiguous").sum()),
            "eligible_in_existing_model":"Not changed by this audit",
            "source_url":str(group.iloc[0]["Official source URL"]),
        })
    return rows

def main():
    prior,current,stats,status=load_saved_data(SPORT)
    official=pd.read_csv(INPUT,dtype={"Team ID":str})
    links=reconcile(official,prior,current,stats)
    official_current=pd.read_csv(CURRENT_INPUT,dtype={"Team ID":str})
    current_links=reconcile(official_current,prior,current,stats)
    teams=summarize(links,prior,current,stats)
    baseline=evidence_adjustments(prior,current,stats,set(official["Team ID"].astype(str)))
    for team in teams:
        tid=team["team_id"]
        before=links.loc[links["Team ID"].eq(tid)]
        after=current_links.loc[current_links["Team ID"].eq(tid)]
        before_verified=before.loc[before["Matched ESPN prior box scores"] & before["ESPN Player ID"].ne("")]
        after_verified=after.loc[after["Matched ESPN current roster"] & after["ESPN Player ID"].ne("")]
        old_ids=set(before_verified["ESPN Player ID"])
        current_ids=set(after_verified["ESPN Player ID"])
        returning=old_ids & current_ids
        sample=stats.loc[stats["Team ID"].astype(str).eq(tid)].copy()
        sample["Minutes"]=pd.to_numeric(sample.get("Minutes"),errors="coerce")
        sample=sample.loc[sample["Player ID"].astype(str).isin(old_ids)]
        total=sample["Minutes"].sum(min_count=1)
        ret=sample.loc[sample["Player ID"].astype(str).isin(returning),"Minutes"].sum(min_count=1)
        verified_complete=(len(before)>=8 and len(before_verified)/len(before)>=.90 and len(after_verified)==len(after))
        team["current_official_roster_players"]=len(after)
        team["current_official_names_confirmed_by_espn_current_roster"]=len(after_verified)
        team["documented_returning_players"]=len(returning)
        team["candidate_returning_minutes_pct"]=(
            (round(100*float(ret)/float(total),2) if pd.notna(ret) else 0.0)
            if verified_complete and pd.notna(total) and total>0 else None
        )
        team["independent_evidence_candidate_eligible"]=bool(verified_complete)
        team["independent_evidence_notes"]="Retrospective comparison, subject to manual review; not automatically an experimental model input."
        team["current_roster_source_url"]=str(after.iloc[0]["Official source URL"]) if not after.empty else ""
        team["existing_model_roster_adjustment"]=baseline.get(tid,{}).get("adjustment")
        team["existing_model_eligible"]=tid in baseline
    OUTPUT.mkdir(parents=True,exist_ok=True)
    links.to_csv(OUTPUT/"linked_players.csv",index=False)
    current_links.to_csv(OUTPUT/"linked_current_players.csv",index=False)
    report={
        "checked_utc":datetime.now(timezone.utc).isoformat(),"division":SPORT,
        "source":"Official 2025-26 and 2026-27 school athletics roster listings + ESPN 2025-26 box scores and season-labeled roster snapshots",
        "limitation":"Sources were checked retrospectively; not proof of pre-November-2026 availability, season-complete ESPN membership, or NCAA eligibility.",
        "model_changed":False,
        "teams":teams
    }
    (OUTPUT/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
    for t in teams:
        print(f"{t['team']}: {t['official_roster_players']} official listed; "
              f"{t['official_names_linked_to_unique_espn_id']} exact IDs; "
              f"{t['official_players_linked_to_prior_stats']} verified ESPN stat matches "
              f"({t['official_to_stats_match_pct']}%); model eligible: {t['existing_model_eligible']}",flush=True)
    print("Saved: "+str(OUTPUT/"summary.json"),flush=True)

if __name__=="__main__":
    main()

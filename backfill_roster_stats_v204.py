#!/usr/bin/env python3
"""V204: resumable, source-only backfill for legacy ESPN roster player totals.

Older archived totals predate per-player game-ID/name provenance. Recollect a
small, upcoming-game prioritized group each run with the existing ESPN
box-score importer; do not manufacture provenance or touch model forecasts.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd

from archive_roster_batch import directory, read, run as refresh_archive
from priority_schedule import upcoming_d1_ids
from collect_official_rosters_v204 import FOLDER,SPORT,choose_targets

ROOT=Path(__file__).resolve().parent

def needing_provenance(manifest, schools, priorities, stats, status=None, limit=8):
    matches=choose_targets(manifest,schools,priorities,len(manifest))
    rows=[]
    for row in matches:
        tid=str(row["Team ID"])
        if not tid:continue
        subset=stats[stats["Team ID"].astype(str).eq(tid)] if not stats.empty and "Team ID" in stats else pd.DataFrame()
        if subset.empty:
            reason="missing_previous_year_stats"
        elif not {"Game IDs","Games with box score","Player"}.issubset(subset.columns):
            reason="legacy_player_game_provenance_columns_missing"
        else:
            games=subset["Game IDs"].fillna("").astype(str).str.strip()
            counts=pd.to_numeric(subset["Games with box score"],errors="coerce")
            names=subset["Player"].fillna("").astype(str).str.strip()
            if (games=="").any() or counts.isna().any() or (counts<=0).any() or (names=="").any():
                reason="one_or_more_players_missing_named_game_provenance"
            else:
                continue
        rows.append({"team_id":tid,"team":row["ESPN Team"],
                    "priority_upcoming":tid in priorities,"reason":reason})
    rows.sort(key=lambda a:(not a["priority_upcoming"],a["team"]))
    return rows[:limit],rows

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,default=8,help="Source-safe roster stats refetch per run (1-12 teams)")
    args=p.parse_args()
    if not 1<=args.limit<=12:p.error("limit must be 1-12")
    folder=ROOT/FOLDER
    manifest=pd.read_csv(folder/"source_manifest.csv",dtype=str,keep_default_na=False)
    schools=directory(SPORT)
    priorities,errors=upcoming_d1_ids(SPORT,set(schools["Team ID"].astype(str)),days=14)
    stats=read("previous_stats",SPORT)
    selected,queue=needing_provenance(manifest,schools,priorities,stats,limit=args.limit)
    print(f"V204 previous-game provenance gap: {len(queue)} schools, selected {len(selected)} now; source errors={len(errors)}",flush=True)
    for row in selected:print(f"  {row['team']}: {row['reason']}",flush=True)
    if selected:
        # Existing collector fetches both season-labeled rosters + completed
        # 2025-26 ESPN player box scores, preserves old records on failures.
        refresh_archive(SPORT,len(selected),team_ids=[x["team_id"] for x in selected])
    report={"version":204,"checked_utc":datetime.now(timezone.utc).isoformat(),
            "division":SPORT,"queued_missing_player_provenance":len(queue),
            "attempted":selected,"source_schedule_errors":errors,
            "note":"This source-only backfill neither changes power ratings nor upgrades teams without corroborated game IDs."}
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"game_provenance_backfill.json").write_text(json.dumps(report,indent=2)+"\n")
    return report

if __name__=="__main__":main()

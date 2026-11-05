"""V231: bounded ESPN boxscore discrepancy inspection, no writes to ratings.

Reports which athlete rows are skipped by the existing V228 parser, so we
never loosen the points reconciliation threshold without identifying evidence.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
from player_stats_import import parse_boxscore, STAT_ALIASES, parse_minutes, numeric
from player_stats_v228 import _fetch_box, ROOT, DIR

SPORT="womens-college-basketball"
COLS=["Game ID","Team ID","Team","Team score","Status","Reason"]


def audit_payload(payload, team_id, score, game_id):
    parsed=parse_boxscore(payload,team_id,game_id)
    parsed_ids={str(r["Player ID"]) for r in parsed}
    raw_groups=[g for g in (payload.get("boxscore") or {}).get("players") or []
                if str((g.get("team") or {}).get("id"))==str(team_id)]
    summary=[]
    missing=[]
    raw_total=0.0
    for group in raw_groups:
        for block in group.get("statistics") or []:
            labels=[str(x).strip().upper() for x in block.get("labels") or block.get("names") or []]
            pts_col=next((i for i,x in enumerate(labels) if x in ("PTS","POINTS")),None)
            if pts_col is None:
                summary.append({"labels":labels,"athletes":len(block.get("athletes") or []),"reason":"NO_PTS_LABEL"})
                continue
            summary.append({"labels":labels,"athletes":len(block.get("athletes") or []),"reason":"PTS_PRESENT"})
            for athlete in block.get("athletes") or []:
                profile=athlete.get("athlete") or {}
                pid=str(profile.get("id") or "")
                name=str(profile.get("displayName") or profile.get("fullName") or "")
                stats=athlete.get("stats") or []
                pts=numeric(stats[pts_col]) if len(stats)>pts_col else None
                if pts is not None:raw_total+=pts
                if pid not in parsed_ids:
                    missing.append({"name":name,"athlete_id":pid,
                                    "points":pts,"stats":stats,
                                    "didNotPlay":athlete.get("didNotPlay"),
                                    "inactive":athlete.get("inactive")})
    return {"team_id":str(team_id),"game_id":str(game_id),
            "reported_team_points":score,
            "parsed_athlete_count":len(parsed),
            "parsed_athlete_points":sum(p["Points"] for p in parsed),
            "raw_pts_column_sum":raw_total,
            "raw_team_groups":len(raw_groups),
            "blocks":summary,
            "unparsed_athlete_rows":missing[:25],
            "unparsed_athlete_rows_count":len(missing)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--max-games",type=int,default=15)
    args=parser.parse_args()
    coverage=args.root/DIR/f"{SPORT}_coverage.csv"
    if not coverage.exists():
        raise FileNotFoundError(f"No saved women's coverage report: {coverage}")
    frame=pd.read_csv(coverage,dtype={"Game ID":str,"Team ID":str})
    pending=frame[frame["Status"].eq("unverified")].head(args.max_games)
    if pending.empty:
        print("No unverified women's team box scores to inspect")
        return
    results=[]
    for _,r in pending.iterrows():
        game_id=str(r["Game ID"]);team_id=str(r["Team ID"])
        payload=_fetch_box(SPORT,game_id)
        details=audit_payload(payload,team_id,r["Team score"],game_id)
        details["team"]=str(r["Team"])
        details["saved_reason"]=str(r["Reason"])
        results.append(details)
    print(json.dumps(results,indent=2))


if __name__=="__main__":
    main()

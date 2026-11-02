"""V201: source-grounded diagnostics for UTEP and Northern Kentucky roster model.
This is a read-only evidence report; no threshold relaxation or synthetic players.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import pandas as pd
from saved_roster_data import load_saved_data, team_saved_analysis
from prospective_roster import evidence_adjustments

SPORT="mens-college-basketball"
TARGETS={"2638":"UTEP Miners","94":"Northern Kentucky Norse"}
OUTPUT=Path("data/roster_target_audit_v201/diagnostics.json")

def ids(df,tid):
    if not isinstance(df,pd.DataFrame) or df.empty or not {"Team ID","Player ID"}.issubset(df.columns):
        return set()
    f=df[df["Team ID"].astype(str).eq(str(tid))]
    return set(f["Player ID"].dropna().astype(str))

def audit_team(tid,name,prev,current,stats,status,qualifying):
    old=ids(prev,tid); new=ids(current,tid); documented=ids(stats,tid)
    covered=old & documented
    match_rate=len(covered)/len(old) if old else 0.0
    current_overlap=len(new & documented)
    old_current_overlap=len(old & new)
    record=None
    if isinstance(status,pd.DataFrame) and not status.empty and "Team ID" in status:
        rows=status[status["Team ID"].astype(str).eq(tid)]
        if not rows.empty:record=rows.iloc[-1]
    source_state=str(record.get("state","unknown")) if record is not None else "unknown"
    saved=team_saved_analysis(tid,prev,current,stats)
    result=saved.get("returning",pd.DataFrame()) if saved else pd.DataFrame()
    row=result.iloc[0] if not result.empty else None
    minutes=pd.to_numeric(row.get("Returning minutes % (known only)"),errors="coerce") if row is not None else None
    valid_minutes=minutes is not None and pd.notna(minutes)
    reason=[]
    if len(old)<8:reason.append("fewer_than_8_prior_roster_players")
    if len(old) and match_rate<.9:reason.append("fewer_than_90pct_prior_players_matched_to_valid_stats")
    if not valid_minutes:reason.append("returning_minutes_not_established")
    if not old or not new:reason.append("missing_season_roster_snapshot")
    if source_state!="collected":reason.append("collector_not_fully_complete")
    qualified=tid in qualifying
    return {
        "team":name,"team_id":tid,
        "previous_roster_players":len(old),"current_roster_players":len(new),
        "valid_player_stat_ids":len(documented),
        "prior_players_with_matching_stats":len(covered),
        "prior_stat_match_pct":round(match_rate*100,1) if old else None,
        "same_team_ids_in_prior_and_current_rosters":old_current_overlap,
        "current_players_with_prior_stats":current_overlap,
        "returning_minutes_pct_known_only":round(float(minutes),2) if valid_minutes else None,
        "collector_state":source_state,
        "boxscores_parsed":int(pd.to_numeric(record.get("Game box scores parsed"),errors="coerce")) if record is not None and pd.notna(pd.to_numeric(record.get("Game box scores parsed"),errors="coerce")) else None,
        "games_in_source_feed":int(pd.to_numeric(record.get("Completed games in feed"),errors="coerce")) if record is not None and pd.notna(pd.to_numeric(record.get("Completed games in feed"),errors="coerce")) else None,
        "experimental_qualified":qualified,
        "raw_roster_scenario_adjustment":qualifying.get(tid,{}).get("adjustment") if qualified else None,
        "blocking_reasons":reason,
        "collector_detail":str(record.get("details",""))[:220] if record is not None else "No collection status",
        "data_limitations":"ESPN season roster and box-score totals may omit players; eligible evidence is provisional, not verified lineup membership."
    }

def main():
    prev,current,stats,status=load_saved_data(SPORT)
    qualified=evidence_adjustments(prev,current,stats,set(TARGETS))
    rows=[audit_team(tid,name,prev,current,stats,status,qualified) for tid,name in TARGETS.items()]
    report={"created_utc":datetime.now(timezone.utc).isoformat(),
            "division":SPORT,
            "roster_experiment_thresholds":{"minimum_prior_roster_players":8,"minimum_prior_stat_match_pct":90},
            "purpose":"Explain matching experimental vs baseline spreads without inventing roster adjustments.",
            "teams":rows}
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(report,indent=2)+"\n")
    for row in rows:
        print(f"ROSTER EVIDENCE: {row['team']} — prior {row['previous_roster_players']}, current {row['current_roster_players']}, stats match {row['prior_players_with_matching_stats']}/{row['previous_roster_players']} ({row['prior_stat_match_pct']}%), qualified={row['experimental_qualified']}, adjustment={row['raw_roster_scenario_adjustment']}, blockers={row['blocking_reasons']}")
    print(f"Report: {OUTPUT}")

if __name__=="__main__": main()

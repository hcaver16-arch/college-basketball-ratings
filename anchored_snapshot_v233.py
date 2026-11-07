"""V233: timestamped research-only preseason-anchored power snapshot.

The output is readable by V97's existing optional experimental model loader.
Official daily_ratings.py and rating_engine.py are intentionally unchanged.

Inputs: only *saved, already-observed* previous-season and current-season ESPN
finals. A snapshot cannot be created from a future game or stale official
rating data. The new model never invents priors for unknown ESPN team IDs.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd
from rating_engine import calculate_power
from prior_transition_research_v229 import anchored_ridge, normalize

SPORTS=("mens-college-basketball","womens-college-basketball")
MODEL_ID="anchored_ridge8_v233"
FIRST_SEASON_DATE="2026-11-01"
OUT_COLS=("Team ID","Power","snapshot_utc","model_id",
          "source_official_snapshot_utc","source_official_sha256",
          "source_previous_sha256","source_current_sha256",
          "training_final_games","source_latest_snapshot_date")


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def create_snapshot(root: Path, sport: str, now: datetime,
                    max_age_hours=48):
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now=now.astimezone(timezone.utc)
    base=root/"data"/"ratings"/sport
    previous_path=base/"history_2025-26.csv.gz"
    current_path=base/"season_2026-27.csv.gz"
    official_path=base/"latest.csv.gz"
    status_path=base/"status.json"
    if any(not x.exists() for x in
           (previous_path,current_path,official_path,status_path)):
        raise RuntimeError(f"{sport}: missing saved source; no experimental snapshot")
    from prospective_archive_v97 import parse_dt
    status=json.loads(status_path.read_text())
    observed=parse_dt(status.get("updated_utc"))
    if observed is None or not 0 <= (now-observed).total_seconds()/3600 <= max_age_hours:
        raise RuntimeError(f"{sport}: official source stale or undated; cannot issue experimental snapshot")
    prev=pd.read_csv(previous_path,dtype={"Home ID":str,"Away ID":str,"Game ID":str})
    current=pd.read_csv(current_path,dtype={"Home ID":str,"Away ID":str,"Game ID":str})
    prior,stats=calculate_power(prev)
    if prior.empty or stats["games"]<1000:
        raise RuntimeError("Insufficient prior-season game data; no experimental model")
    pre=dict(zip(prior["Team ID"].astype(str), prior["Power"].astype(float)))
    saved_official=pd.read_csv(official_path,dtype={"Team ID":str})
    if "Team ID" not in saved_official or "Preseason rating" not in saved_official:
        raise RuntimeError("Official snapshot has no auditable preseason baseline")
    official_pre=dict(zip(saved_official["Team ID"].astype(str),
                          pd.to_numeric(saved_official["Preseason rating"],errors="coerce")))
    for tid,value in pre.items():
        if tid not in official_pre or not np.isfinite(official_pre[tid]) or abs(official_pre[tid]-value)>.025:
            raise RuntimeError(f"{sport}: previous-season fit diverges from official preseason rating for {tid}")
    usable=normalize(current,"V233 saved current season")
    # Team names and local dates are supplied by the saved ESPN fetch, not
    # guessed from scheduled results. Reject future-date final records.
    today=now.astimezone(__import__("zoneinfo").ZoneInfo("America/New_York")).date()
    if (usable["Day"]>today).any() or (usable["Day"].astype(str)<FIRST_SEASON_DATE).any():
        raise RuntimeError(f"{sport}: impossible current-season final dates")
    values=anchored_ridge(pre,usable)
    if not values or not all(np.isfinite(x) for x in values.values()):
        raise RuntimeError("Cannot fit safe anchored ratings")
    # A new/transition team without a 2025-26 rating is excluded; do not
    # publish its unvalidated neutral-zero initialization as a team forecast.
    names=sorted(pre)
    output=pd.DataFrame({
        "Team ID":names,
        "Power":[float(values[k]) for k in names],
        "snapshot_utc":now.isoformat(timespec="seconds").replace("+00:00","Z"),
        "model_id":MODEL_ID,
        "source_official_snapshot_utc":observed.isoformat().replace("+00:00","Z"),
        "source_official_sha256":digest(official_path),
        "source_previous_sha256":digest(previous_path),
        "source_current_sha256":digest(current_path),
        "training_final_games":len(usable),
        "source_latest_snapshot_date":str(status.get("snapshot_date","")),
    })
    if output["Team ID"].duplicated().any():
        raise RuntimeError("Duplicate anchored ratings")
    return output


def write_snapshot(root: Path, sport: str, frame: pd.DataFrame):
    path=root/"data"/"prospective"/"experimental_ratings"/sport/"latest.csv.gz"
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix="anchored-",dir=path.parent,suffix=".csv.gz")
    os.close(fd)
    try:
        frame.to_csv(tmp,index=False,compression="gzip")
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return path


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("."))
    p.add_argument("--sport",choices=["both",*SPORTS],default="both")
    args=p.parse_args()
    now=datetime.now(timezone.utc)
    results={}
    for sport in SPORTS if args.sport=="both" else [args.sport]:
        frame=create_snapshot(args.root,sport,now)
        path=write_snapshot(args.root,sport,frame)
        results[sport]={"teams_with_preseason_anchor":len(frame),
                        "training_finals":int(frame.iloc[0]["training_final_games"]),
                        "snapshot_utc":str(frame.iloc[0]["snapshot_utc"]),
                        "model_id":MODEL_ID,"path":str(path)}
    print(json.dumps({"status":"EXPERIMENTAL_ONLY", "divisions":results},indent=2))


if __name__=="__main__":
    main()

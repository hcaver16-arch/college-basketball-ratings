"""V133 read-only opening-game monitoring based on committed forecast archives."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent / "data"
SPORTS = {"Men's": "mens-college-basketball", "Women's": "womens-college-basketball"}

@st.cache_data(ttl=120, show_spinner=False)
def _status(sport):
    path = ROOT / "predictions" / sport / "status.json"
    return json.loads(path.read_text()) if path.exists() else None

@st.cache_data(ttl=120, show_spinner=False)
def _forecasts(sport):
    path = ROOT / "predictions" / sport / "first_forecasts.csv.gz"
    return pd.read_csv(path, dtype={"Game ID": str}) if path.exists() else pd.DataFrame()

@st.cache_data(ttl=120, show_spinner=False)
def _evaluations(sport):
    path = ROOT / "predictions" / sport / "evaluated_games.csv.gz"
    return pd.read_csv(path, dtype={"Game ID": str}) if path.exists() else pd.DataFrame()

def summarize(forecasts, evaluations, status, now=None):
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None: now = now.tz_localize("UTC")
    report = {"saved": len(forecasts), "pre_tip": 0, "upcoming": 0,
              "completed": 0, "d1_completed": 0, "issues": []}
    if status is None:
        report["issues"].append("No prediction refresh status has been saved yet")
    else:
        updated = pd.to_datetime(status.get("updated_utc"), utc=True, errors="coerce")
        if pd.isna(updated):
            report["issues"].append("Prediction refresh time is missing")
        elif (now - updated).total_seconds() > 48 * 3600:
            report["issues"].append("Prediction refresh is more than 48 hours old")
        diagnostics = status.get("forecast_diagnostics") or {}
        for field, label in (("missing_rating", "Upcoming games with an unrated opponent"),
                             ("baseline_eligible", "Newly eligible first forecasts")):
            report[label] = int(diagnostics.get(field, 0))
    if not forecasts.empty:
        required = {"Game ID", "Game start UTC", "First forecast UTC"}
        if required.issubset(forecasts):
            start = pd.to_datetime(forecasts["Game start UTC"], utc=True, errors="coerce")
            created = pd.to_datetime(forecasts["First forecast UTC"], utc=True, errors="coerce")
            valid = start.notna() & created.notna() & (created < start)
            report["pre_tip"] = int(valid.sum())
            report["upcoming"] = int((valid & (start > now)).sum())
            invalid = int((~valid).sum())
            if invalid: report["issues"].append(f"{invalid} saved forecasts lack valid pre-tip timestamps")
            duplicates = int(forecasts["Game ID"].duplicated().sum())
            if duplicates: report["issues"].append(f"{duplicates} duplicate forecast IDs")
        else:
            report["issues"].append("Forecast archive is missing required columns")
    if not evaluations.empty:
        needed = {"Game ID", "Game start UTC", "First forecast UTC"}
        if needed.issubset(evaluations):
            start = pd.to_datetime(evaluations["Game start UTC"], utc=True, errors="coerce")
            created = pd.to_datetime(evaluations["First forecast UTC"], utc=True, errors="coerce")
            good = created.notna() & start.notna() & (created < start)
            valid_e = evaluations.loc[good].drop_duplicates("Game ID")
            report["completed"] = len(valid_e)
            if "Matchup class" in valid_e:
                report["d1_completed"] = int(valid_e["Matchup class"].eq("D1 vs D1").sum())
        else:
            report["issues"].append("Evaluation archive is missing required columns")
    return report

def render_opening_game_monitor_v133():
    st.subheader("Opening-game monitoring · 2026–27")
    st.caption("Read-only snapshots from committed GitHub data. Forecasts are counted only when their saved timestamp is before tipoff; figures update after scheduled archive jobs run.")
    selected = st.selectbox("Monitor division", list(SPORTS), key="v133_division")
    sport = SPORTS[selected]
    try:
        status = _status(sport)
        f = _forecasts(sport)
        e = _evaluations(sport)
        summary = summarize(f,e,status)
    except Exception as exc:
        st.warning(f"Opening-game monitoring data unavailable: {exc}")
        return
    from forecast_coverage_v134 import render_coverage_v134
    render_coverage_v134(sport, f, e, status)
    a,b,c,d = st.columns(4)
    a.metric("First forecasts saved", summary["saved"])
    b.metric("Verifiable pre-tip", summary["pre_tip"])
    c.metric("Upcoming with forecasts", summary["upcoming"])
    d.metric("Completed D1 graded", summary["d1_completed"])
    st.caption(f"{summary['completed']} graded games across all opponent classes.")
    if status is not None:
        st.caption(f"Last prediction refresh (UTC): {status.get('updated_utc','unknown')}")
        diagnostics = status.get("forecast_diagnostics") or {}
        with st.expander("Latest forecast-collection diagnostics"):
            st.json(diagnostics)
            st.caption("These diagnostic counts describe the latest refresh window, not the full season. Missing ratings do not necessarily mean an eligible D1 forecast was skipped.")
    if summary["issues"]:
        for issue in summary["issues"]: st.warning(issue)
    elif summary["completed"] == 0:
        st.info("No games have been graded yet. Once finals are archived, completed-game counts will appear automatically.")
    else:
        st.success("Saved prediction timestamps are valid in the available archives.")

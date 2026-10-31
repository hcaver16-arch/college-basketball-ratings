"""V134: read-only, bounded forecast coverage for observed final results and latest collection window."""
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent / "data"

@st.cache_data(ttl=120, show_spinner=False)
def read_season_and_classes(sport):
    base = ROOT / "ratings" / sport / "season_2026-27.csv.gz"
    classes = ROOT / "predictions" / sport / "game_classification.csv.gz"
    season = pd.read_csv(base, dtype={"Game ID":str}) if base.exists() else pd.DataFrame()
    classification = pd.read_csv(classes, dtype={"Game ID":str}) if classes.exists() else pd.DataFrame()
    return season, classification

def coverage_report(forecasts, evaluations, season, classifications, status):
    """Count only observed games; never imply unseen ESPN games were covered."""
    d = (status or {}).get("forecast_diagnostics") or {}
    observed = {k:int(d.get(k,0)) for k in ("schedule_games","future_scheduled_games",
        "previously_archived","missing_rating","baseline_eligible","not_scheduled",
        "not_future_or_invalid_time")}
    observed["accounted_for_future"] = (observed["previously_archived"] +
        observed["missing_rating"] + observed["baseline_eligible"])
    observed["future_reconciled"] = observed["accounted_for_future"] == observed["future_scheduled_games"]
    output={"latest_window":observed,"observed_finals":0,"finals_with_forecast":0,
            "finals_without_forecast":0,"forecasted_finals_awaiting_grading":0,
            "known_d1_finals_without_forecast":0,"unclassified_missing_finals":0}
    needed={"Game ID","Status"}
    if season.empty or not needed.issubset(season): return output
    finals=season.loc[season["Status"].eq("Final"),["Game ID"]].dropna().drop_duplicates()
    finalids=set(finals["Game ID"].astype(str))
    archived=set(forecasts["Game ID"].dropna().astype(str)) if "Game ID" in forecasts else set()
    graded=set(evaluations["Game ID"].dropna().astype(str)) if "Game ID" in evaluations else set()
    covered=finalids & archived
    missing=finalids - archived
    output.update(observed_finals=len(finalids),finals_with_forecast=len(covered),
        finals_without_forecast=len(missing),forecasted_finals_awaiting_grading=len(covered-graded))
    if {"Game ID","Matchup class"}.issubset(classifications.columns):
        classmap=dict(zip(classifications["Game ID"].astype(str),classifications["Matchup class"]))
        output["known_d1_finals_without_forecast"]=sum(classmap.get(g)=="D1 vs D1" for g in missing)
        output["unclassified_missing_finals"]=sum(g not in classmap for g in missing)
    else:
        output["unclassified_missing_finals"]=len(missing)
    return output

def render_coverage_v134(sport, forecasts, evaluations, status):
    st.markdown("#### Forecast coverage · V134")
    st.caption("Scope: games in the saved season-results archive and the most recent 14-day collection window. This is not a complete independent audit of every NCAA game.")
    try:
        season, classes=read_season_and_classes(sport)
        r=coverage_report(forecasts,evaluations,season,classes,status)
    except Exception as exc:
        st.warning(f"Coverage data unavailable: {exc}")
        return
    window=r["latest_window"]
    a,b,c=st.columns(3)
    a.metric("Future scheduled in latest scan",window["future_scheduled_games"])
    b.metric("Previously forecasted",window["previously_archived"])
    c.metric("Unrated opponents",window["missing_rating"])
    st.caption(f"New eligible forecasts in latest scan: {window['baseline_eligible']} · "
               f"Window counts reconcile: {'Yes' if window['future_reconciled'] else 'No — inspect pipeline'}")
    if not window["future_reconciled"]:
        st.warning("Latest collected future-scheduled game counts do not reconcile.")
    a,b,c=st.columns(3)
    a.metric("Observed final games",r["observed_finals"])
    b.metric("Finals without first forecast",r["finals_without_forecast"])
    c.metric("Forecasted finals awaiting grading",r["forecasted_finals_awaiting_grading"])
    if r["finals_without_forecast"]:
        st.warning(f"{r['known_d1_finals_without_forecast']} known D1 vs D1 finals lack forecasts; "
                   f"{r['unclassified_missing_finals']} missing-forecast finals lack classification.")
    elif r["observed_finals"]:
        st.caption("Every observed final in the saved season archive has a forecast record. This does not establish coverage of games missing from the season archive.")
    else:
        st.info("No final results in the saved season archive yet.")

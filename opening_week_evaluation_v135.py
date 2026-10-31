"""V135: first-week game-level model evaluation from locked pre-tip predictions."""
import pandas as pd
import streamlit as st

def opening_week_metrics(evaluations, season, classifications):
    result={"observed_finals":0,"graded_d1":0,"winner_sample":0,
            "baseline_accuracy":None,"baseline_mae":None,"paired":0,
            "paired_baseline_mae":None,"paired_roster_mae":None,
            "finals_without_forecast":0,"forecasted_finals_ungraded":0,
            "rejected_non_pretip":0,"details":pd.DataFrame()}
    if not season.empty and {"Game ID","Status"}.issubset(season.columns):
        finals=set(season.loc[season["Status"].eq("Final"),"Game ID"].dropna().astype(str))
        result["observed_finals"]=len(finals)
    else: finals=set()
    if evaluations.empty: return result
    required={"Game ID","Game start UTC","First forecast UTC","Actual home margin",
              "Baseline home margin","Matchup class"}
    if not required.issubset(evaluations.columns): return result
    e=evaluations.copy()
    e["Game ID"]=e["Game ID"].astype(str)
    start=pd.to_datetime(e["Game start UTC"],utc=True,errors="coerce")
    forecast=pd.to_datetime(e["First forecast UTC"],utc=True,errors="coerce")
    valid=start.notna() & forecast.notna() & (forecast < start)
    result["rejected_non_pretip"]=int((~valid).sum())
    e=e.loc[valid & e["Matchup class"].eq("D1 vs D1")].drop_duplicates("Game ID").copy()
    for name in ["Actual home margin","Baseline home margin","Later roster margin"]:
        if name in e.columns:e[name]=pd.to_numeric(e[name],errors="coerce")
    e=e.dropna(subset=["Actual home margin","Baseline home margin"])
    result["graded_d1"]=len(e)
    if not len(e):return result
    actual=e["Actual home margin"]; baseline=e["Baseline home margin"]
    e["Baseline error"]=(actual-baseline).abs()
    result["baseline_mae"]=float(e["Baseline error"].mean())
    winner=(actual!=0)&(baseline!=0)
    result["winner_sample"]=int(winner.sum())
    if winner.any():result["baseline_accuracy"]=float(((actual[winner]>0)==(baseline[winner]>0)).mean())
    if {"Roster forecast UTC","Later roster margin"}.issubset(e.columns):
        timestamp=pd.to_datetime(e["Roster forecast UTC"],utc=True,errors="coerce")
        start=pd.to_datetime(e["Game start UTC"],utc=True,errors="coerce")
        paired=e.loc[timestamp.notna()&(timestamp<start)&e["Later roster margin"].notna()]
        result["paired"]=len(paired)
        if len(paired):
            result["paired_baseline_mae"]=float((paired["Actual home margin"]-paired["Baseline home margin"]).abs().mean())
            result["paired_roster_mae"]=float((paired["Actual home margin"]-paired["Later roster margin"]).abs().mean())
    result["details"]=e
    return result

def render_opening_week_evaluation_v135(evaluations, season, classifications):
    st.markdown("#### Opening-week model evaluation · V135")
    st.caption("Only independently archived pre-tip D1 vs D1 forecasts; roster comparison uses matching games. Fewer than 100 games is preliminary.")
    report=opening_week_metrics(evaluations,season,classifications)
    if report["rejected_non_pretip"]:
        st.warning(f"{report['rejected_non_pretip']} late/invalid forecast rows were excluded.")
    if not report["graded_d1"]:
        st.info("No completed D1 games with valid saved forecasts have been graded yet.")
        return
    if report["graded_d1"]<100:
        st.info(f"Preliminary sample: {report['graded_d1']} D1 games (100-game review checkpoint).")
    a,b,c=st.columns(3)
    a.metric("Graded D1 games",report["graded_d1"])
    b.metric("Baseline margin MAE",f"{report['baseline_mae']:.2f} pts")
    c.metric("Winner accuracy",f"{report['baseline_accuracy']:.1%}" if report["baseline_accuracy"] is not None else "—")
    st.caption(f"Winner accuracy based on {report['winner_sample']} non-tied predictions and outcomes.")
    st.markdown("**Paired roster comparison**")
    if report["paired"]:
        a,b,c=st.columns(3)
        a.metric("Paired games",report["paired"])
        b.metric("Baseline MAE (paired)",f"{report['paired_baseline_mae']:.2f} pts")
        c.metric("Roster MAE (paired)",f"{report['paired_roster_mae']:.2f} pts")
        st.caption("Small differences are not evidence of model superiority without larger, independent samples.")
    else:
        st.caption("No eligible paired pre-tip roster forecasts graded yet.")
    with st.expander("Game-level graded results"):
        wanted=[x for x in ["Game ID","Away","Home","Game start UTC","Baseline home margin",
                            "Actual home margin","Baseline error","Later roster margin"] if x in report["details"]]
        st.dataframe(report["details"][wanted],hide_index=True,use_container_width=True)

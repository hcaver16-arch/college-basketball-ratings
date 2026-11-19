"""Courtside V242: read-only breakdown of verified first-forecast performance.

Uses the V123 timestamp-validated D1-only evaluation archive. No training,
forecast regeneration, archive edits, or changes to official ratings.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
from live_performance_v123 import _read, _graded, DIVISIONS


def accuracy_rows(evaluated: pd.DataFrame):
    games, rejected = _graded(evaluated)
    if games.empty or "Matchup class" not in games.columns:
        return pd.DataFrame(), rejected
    d1 = games.loc[games["Matchup class"].eq("D1 vs D1")].copy()
    if d1.empty:
        return d1, rejected
    d1["Abs predicted margin"] = d1["Baseline home margin"].abs()
    d1["Favorite size"] = pd.cut(
        d1["Abs predicted margin"], bins=[-0.001, 5, 10, 20, np.inf],
        labels=["0–5", "5–10", "10–20", "20+"], include_lowest=True
    )
    d1["Predicted winner"] = np.where(d1["Baseline home margin"] > 0, "Home", "Away")
    d1["Week"] = pd.to_datetime(d1["Game start UTC"], utc=True).dt.to_period("W").astype(str)
    d1["Signed error"] = d1["Actual home margin"] - d1["Baseline home margin"]
    return d1, rejected


def summarize(frame: pd.DataFrame, group: str):
    if frame.empty:
        return pd.DataFrame(columns=[group, "Games", "MAE", "Bias", "Winner accuracy", "Decisive games"])
    rows = []
    for key, games in frame.groupby(group, observed=True, sort=True):
        decisive = games.loc[games["Baseline winner eligible"]]
        rows.append({
            group: str(key), "Games": len(games),
            "MAE": round(float(games["Baseline error"].mean()), 2),
            "Bias": round(float(games["Signed error"].mean()), 2),
            "Winner accuracy": round(100 * float(decisive["Baseline winner correct"].mean()), 1) if len(decisive) else np.nan,
            "Decisive games": len(decisive),
        })
    return pd.DataFrame(rows)


def render_accuracy_v242():
    st.markdown("### V242 · Prediction accuracy audit")
    st.caption("Research-only. Saved first forecasts, completed D1 vs D1 games, and verified pre-tip timestamps. "
               "MAE and signed bias are in points; accuracy excludes predicted and actual ties.")
    division = st.selectbox("Division", list(DIVISIONS), key="v242_division")
    try:
        _, raw = _read(DIVISIONS[division])
        games, rejected = accuracy_rows(raw)
    except (OSError, ValueError, KeyError, TypeError, pd.errors.ParserError) as exc:
        st.warning(f"V242 evaluation unavailable: {exc}")
        return
    if rejected:
        st.warning(f"{rejected} rows excluded because a valid pre-tip forecast could not be verified.")
    if games.empty:
        st.info("No verified completed D1 vs D1 forecasts available.")
        return
    dates = sorted(games["Game day"].unique())
    start, end = st.select_slider("Game dates", options=dates, value=(dates[0], dates[-1]), key="v242_dates")
    subset = games.loc[games["Game day"].between(start, end)].copy()
    decisive = subset.loc[subset["Baseline winner eligible"]]
    a, b, c, d = st.columns(4)
    a.metric("D1 games", len(subset))
    b.metric("Margin MAE", f"{subset['Baseline error'].mean():.2f}" if len(subset) else "—")
    c.metric("Winner accuracy", f"{100*decisive['Baseline winner correct'].mean():.1f}%" if len(decisive) else "—")
    d.metric("Signed bias", f"{subset['Signed error'].mean():+.2f}" if len(subset) else "—")
    st.caption("Signed bias = actual home margin minus predicted home margin. Positive values mean home teams "
               "outperformed the model; negative values mean they underperformed.")
    if len(subset):
        weekly = summarize(subset, "Week")
        st.markdown("**Performance by week**")
        st.line_chart(weekly.set_index("Week")[["MAE"]])
        st.dataframe(weekly, hide_index=True, use_container_width=True)
        left, right = st.columns(2)
        with left:
            st.markdown("**By predicted favorite size**")
            st.dataframe(summarize(subset, "Favorite size"), hide_index=True, use_container_width=True)
        with right:
            st.markdown("**By predicted winner location**")
            st.dataframe(summarize(subset, "Predicted winner"), hide_index=True, use_container_width=True)
        st.markdown("**Largest missed margins**")
        columns = [c for c in ("Game day", "Away", "Home", "Baseline home margin",
                   "Actual home margin", "Baseline error", "Signed error") if c in subset.columns]
        st.dataframe(subset.nlargest(15, "Baseline error")[columns], hide_index=True, use_container_width=True)
        st.download_button("Download V242 graded D1 audit", subset.to_csv(index=False).encode(),
                           file_name=f"courtside_v242_{DIVISIONS[division]}.csv",
                           mime="text/csv", key="v242_download")
    st.caption("Observational audit only: these descriptive slices do not establish causation or authorize model changes. "
               "Use chronological out-of-sample research before the January 1 evaluation.")

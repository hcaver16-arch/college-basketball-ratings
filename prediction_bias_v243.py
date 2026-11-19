"""V243: read-only prospective bias decomposition, not a model calibration.

V239/V240 provide separate chronological retrospective research; this module
uses only immutable, verified pre-tip V123 outcomes for 2026-27.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import streamlit as st
from prediction_accuracy_v242 import accuracy_rows
from live_performance_v123 import _read, DIVISIONS

MIN_N = 20


def prepare(raw):
    frame, rejected = accuracy_rows(raw)
    if frame.empty:
        return frame, rejected
    frame = frame.copy()
    frame["Predicted favorite"] = np.where(frame["Baseline home margin"] > 0, "Home",
                                   np.where(frame["Baseline home margin"] < 0, "Away", "Tie"))
    frame["Favorite magnitude"] = pd.cut(frame["Abs predicted margin"],
        [-0.001, 5, 10, 20, np.inf], labels=["0–5", "5–10", "10–20", "20+"])
    frame["Actual blowout over 40"] = np.where(frame["Actual home margin"].abs() > 40, "Yes", "No")
    frame["Predicted home margin"] = frame["Baseline home margin"]
    frame["Actual home margin numeric"] = frame["Actual home margin"]
    return frame, rejected


def segment(frame, columns):
    if frame.empty:
        return pd.DataFrame()
    rows = []
    for keys, group in frame.groupby(columns, observed=True, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        n = len(group)
        residual = group["Signed error"].to_numpy(dtype=float)
        winner = group.loc[group["Baseline winner eligible"]]
        rows.append({**dict(zip(columns, map(str, keys))), "Games": n,
          "Predicted home margin": round(float(group["Baseline home margin"].mean()), 2),
          "Actual home margin": round(float(group["Actual home margin"].mean()), 2),
          "Bias": round(float(residual.mean()), 2),
          "MAE": round(float(np.abs(residual).mean()), 2),
          "Bias SE": round(float(residual.std(ddof=1) / np.sqrt(n)), 2) if n > 1 else np.nan,
          "Winner accuracy %": round(float(100 * winner["Baseline winner correct"].mean()), 1) if len(winner) else np.nan,
          "Sample caution": "Small sample" if n < MIN_N else ""})
    return pd.DataFrame(rows)


def constant_shift_sensitivity(frame, shifts=(0, 2, 4, 6)):
    """Descriptive fixed offsets, NOT fitted/published alternative forecasts."""
    if frame.empty:
        return pd.DataFrame()
    result = []
    for shift in shifts:
        # Only for designated home games when a trusted site flag exists.
        # V123 does not guarantee this flag, so label as unconditional sensitivity.
        pred = frame["Baseline home margin"].to_numpy(dtype=float) + shift
        actual = frame["Actual home margin"].to_numpy(dtype=float)
        eligible = (pred != 0) & (actual != 0)
        result.append({"Added to every predicted home margin": shift,
            "Games": len(frame), "MAE": round(float(np.abs(actual-pred).mean()), 2),
            "Signed bias": round(float((actual-pred).mean()), 2),
            "Winner accuracy %": round(float(100*np.mean((pred[eligible]>0)==(actual[eligible]>0))), 1) if eligible.any() else np.nan})
    return pd.DataFrame(result)


def render_bias_v243():
    st.markdown("### V243 · Prediction bias investigation")
    st.caption("Research-only diagnostic using the same verified pre-tip D1 outcomes as V242. "
        "This does not estimate a causal home-court advantage or change forecasts.")
    division = st.selectbox("Division for bias audit", list(DIVISIONS), key="v243_division")
    try:
        _, raw = _read(DIVISIONS[division])
        frame, rejected = prepare(raw)
    except (OSError, ValueError, KeyError, TypeError, pd.errors.ParserError) as exc:
        st.warning(f"Bias investigation unavailable: {exc}")
        return
    if rejected:
        st.warning(f"{rejected} invalid pre-tip records excluded.")
    if frame.empty:
        st.info("No eligible D1 forecasts to investigate.")
        return
    st.markdown("**Separate predicted home and away favorites by margin**")
    st.dataframe(segment(frame, ["Predicted favorite", "Favorite magnitude"]), hide_index=True, use_container_width=True)
    st.caption("Bias = actual home margin minus forecast home margin. Positive bias is not automatically "
               "home-court advantage: schedule selection, preseason scale, opponent quality, and site mix are confounders.")
    st.markdown("**Observed blowouts (outcome-only diagnostic)**")
    st.dataframe(segment(frame, ["Actual blowout over 40"]), hide_index=True, use_container_width=True)
    st.caption("The 40-point category is defined AFTER results and cannot be used to make pregame predictions. "
               "It does not by itself test the model's 40-point training cap.")
    st.markdown("**Unconditional home-margin offset sensitivity**")
    st.dataframe(constant_shift_sensitivity(frame), hide_index=True, use_container_width=True)
    st.caption("Offsets are applied to ALL games, including neutral-site games, because this V123 archive "
               "does not verify venue flags. They are illustrative sensitivities, NOT candidate HCA estimates "
               "and NOT time-ordered out-of-sample model comparisons.")
    st.markdown("**Historical research cross-check**")
    st.info("Existing V239 and V240 already implement chronological retrospective tests of 20/40/60-point "
            "training caps, home-court assumptions, preseason scale and home-team selection. "
            "Compare those research outputs separately before making any model recommendation; "
            "do not treat retrospective reconstructions as locked prospective forecasts.")
    st.download_button("Download V243 pre-tip D1 diagnostic", frame.to_csv(index=False).encode(),
        file_name=f"courtside_v243_{DIVISIONS[division]}.csv", mime="text/csv", key="v243_download")

"""V123 read-only performance panel for immutable first-forecast archives."""
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent / "data" / "predictions"
DIVISIONS = {"Men's": "mens-college-basketball", "Women's": "womens-college-basketball"}


def _read(sport):
    base = ROOT / sport
    evaluated = base / "evaluated_games.csv.gz"
    forecasts = base / "first_forecasts.csv.gz"
    f = pd.read_csv(forecasts, compression="gzip", dtype={"Game ID": str}) if forecasts.exists() else pd.DataFrame()
    e = pd.read_csv(evaluated, compression="gzip", dtype={"Game ID": str}) if evaluated.exists() else pd.DataFrame()
    return f, e


def _graded(e):
    required = {"Game ID", "Game start UTC", "First forecast UTC",
                "Baseline home margin", "Actual home margin"}
    if e.empty:
        return pd.DataFrame(), 0
    if not required.issubset(e.columns):
        raise ValueError("Evaluation archive is missing: " + ", ".join(sorted(required - set(e.columns))))
    e = e.copy()
    start = pd.to_datetime(e["Game start UTC"], utc=True, errors="coerce")
    saved = pd.to_datetime(e["First forecast UTC"], utc=True, errors="coerce")
    allowed = start.notna() & saved.notna() & (saved < start)
    rejected = int((~allowed).sum())
    e = e.loc[allowed].copy()
    e = e.drop_duplicates("Game ID", keep="first")
    for c in ("Baseline home margin", "Actual home margin", "Later roster margin"):
        if c in e.columns:
            e[c] = pd.to_numeric(e[c], errors="coerce")
    e = e.dropna(subset=["Baseline home margin", "Actual home margin"])
    if e.empty:
        return e, rejected
    e["Game day"] = pd.to_datetime(e["Game start UTC"], utc=True).dt.date
    e["Month"] = pd.to_datetime(e["Game start UTC"], utc=True).dt.strftime("%Y-%m")
    e["Baseline error"] = (e["Actual home margin"] - e["Baseline home margin"]).abs()
    e["Baseline winner correct"] = ((e["Actual home margin"] > 0) == (e["Baseline home margin"] > 0))
    e["Baseline winner eligible"] = (e["Actual home margin"] != 0) & (e["Baseline home margin"] != 0)
    if "Roster forecast UTC" in e.columns:
        roster_time = pd.to_datetime(e["Roster forecast UTC"], utc=True, errors="coerce")
    else:
        roster_time = pd.to_datetime(e.get("Roster forecast UTC", pd.Series(pd.NaT, index=e.index)), utc=True, errors="coerce")
    # The evaluation joins the separately timestamped roster forecast under this field.
    roster_margin = e["Later roster margin"] if "Later roster margin" in e else pd.Series(float("nan"), index=e.index)
    e["Roster valid"] = roster_time.notna() & (roster_time < pd.to_datetime(e["Game start UTC"], utc=True)) & roster_margin.notna()
    e["Roster error"] = (e["Actual home margin"] - roster_margin).abs().where(e["Roster valid"])
    e["Roster winner correct"] = ((e["Actual home margin"] > 0) == (roster_margin > 0))
    e["Roster winner eligible"] = e["Roster valid"] & (e["Actual home margin"] != 0) & (roster_margin != 0)
    return e, rejected


def _pct(frame, correct, eligible):
    sub = frame.loc[frame[eligible]]
    return f"{sub[correct].mean():.1%}" if len(sub) else "—"


def _score(frame):
    if frame.empty:
        return {"Games": 0, "MAE": "—", "Winner accuracy": "—"}
    return {"Games": len(frame), "MAE": f"{frame['Baseline error'].mean():.2f}",
            "Winner accuracy": _pct(frame, "Baseline winner correct", "Baseline winner eligible")}


def render_live_performance_v123():
    st.markdown("### Live model performance · 2026–27")
    st.caption("Graded from archived pre-tip predictions and saved final scores. Read-only. "
               "The primary view is D1 vs D1; exploratory model comparisons use identical games.")
    chosen = st.selectbox("Division for live performance", list(DIVISIONS), key="v123_division")
    try:
        forecasts, raw = _read(DIVISIONS[chosen])
        games, rejected = _graded(raw)
    except Exception as exc:
        st.warning(f"Performance data could not be loaded: {exc}")
        return
    if rejected:
        st.warning(f"{rejected} evaluation row(s) omitted because their first forecasts were not verifiably pre-tip.")
    total = len(forecasts)
    if games.empty:
        st.metric("Saved first forecasts", total)
        st.info("No completed games with valid pre-tip baseline predictions yet. Metrics will appear after final scores are archived.")
        return
    if "Matchup class" not in games:
        st.warning("D1 matchup classification is missing. No D1-only accuracy will be claimed.")
        return
    d1 = games.loc[games["Matchup class"].eq("D1 vs D1")].copy()
    st.caption(f"{total:,} archived first forecasts · {len(games):,} graded across all opponent classes · {len(d1):,} graded D1 matchups")
    if d1.empty:
        st.info("No completed D1 vs D1 games eligible for evaluation yet.")
        return
    score = _score(d1)
    a, b, c = st.columns(3)
    a.metric("Graded D1 games", score["Games"])
    b.metric("Baseline spread MAE", score["MAE"])
    c.metric("Baseline winner accuracy", score["Winner accuracy"])
    st.caption("MAE measures absolute error in predicted home-team scoring margin (points). "
               "Winner accuracy excludes predicted ties and actual ties.")
    monthly = d1.groupby("Month", as_index=False).agg(Games=("Game ID", "size"), MAE=("Baseline error", "mean"))
    st.markdown("**Performance by month**")
    st.line_chart(monthly.set_index("Month")["MAE"])
    st.dataframe(monthly.round(2), use_container_width=True, hide_index=True)
    paired = d1.loc[d1["Roster valid"]].copy()
    st.markdown("**Baseline versus roster experiment — paired games only**")
    if paired.empty:
        st.info("No completed D1 matchups have a separately timestamped, valid pre-tip roster forecast yet.")
    else:
        p1, p2, p3 = st.columns(3)
        p1.metric("Paired D1 games", len(paired))
        p2.metric("Baseline paired MAE", f"{paired['Baseline error'].mean():.2f}")
        p3.metric("Roster paired MAE", f"{paired['Roster error'].mean():.2f}")
        st.caption("Same games for both models. Baseline winner accuracy: "
                   + _pct(paired, "Baseline winner correct", "Baseline winner eligible")
                   + " · Roster winner accuracy: "
                   + _pct(paired, "Roster winner correct", "Roster winner eligible")
                   + ". The roster model is experimental, not a promoted production model.")
    with st.expander("Graded D1 games and CSV download"):
        cols = [c for c in ("Game day", "Away", "Home", "Baseline home margin",
                            "Actual home margin", "Baseline error", "Later roster margin",
                            "Roster error", "First forecast UTC") if c in d1.columns]
        st.dataframe(d1[cols].sort_values("Game day", ascending=False), hide_index=True, use_container_width=True)
        st.download_button("Download graded D1 games", d1.to_csv(index=False).encode(),
                           file_name="courtside_v123_" + DIVISIONS[chosen] + ".csv",
                           mime="text/csv", key="v123_download")

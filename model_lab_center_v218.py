"""Courtside V218 Model Lab dashboard — read-only presentation over saved forecasts.

No model fitting, prediction updates, or archive writes occur here.
Metrics reuse V123's verified pre-tip game grading and D1-only filters.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

import pandas as pd
import streamlit as st

from live_performance_v123 import _read, _graded, _score


ROOT = Path(__file__).resolve().parent / "data" / "predictions"
SECTIONS = ("Overview", "Performance", "Predictions", "Roster Research", "Advanced Tools")

STYLE = """
<style>
.cs218-hero{background:#fff;border:1px solid #dbe5f2;border-top:4px solid #2863b6;
 border-radius:15px;padding:18px 21px;margin:0 0 14px;box-shadow:0 2px 10px rgba(20,54,101,.04)}
.cs218-eyebrow{font-size:.7rem;letter-spacing:.09em;color:#4675a9;font-weight:850;text-transform:uppercase}
.cs218-hero h2{font-size:1.52rem;color:#183965;line-height:1.2;font-weight:850;margin:6px 0}
.cs218-hero p{color:#677c97;font-size:.84rem;margin:0}
.cs218-subhead{font-size:1.08rem;font-weight:850;color:#1e426e;margin:16px 0 8px}
.cs218-explain{font-size:.8rem;line-height:1.55;color:#667b95}
.st-key-cs218_lab_nav [data-testid="stSegmentedControl"]{margin-bottom:9px}
@media(max-width:700px){
 .cs218-hero{padding:14px}.cs218-hero h2{font-size:1.26rem}
 .st-key-cs218_lab_nav [role="radiogroup"]{flex-wrap:wrap}
}
</style>
"""


def render_model_lab_header(league: str):
    """Display compact primary navigation; only one workstream is rendered."""
    st.markdown(STYLE, unsafe_allow_html=True)
    st.html(
        '<div class="cs218-hero">'
        '<div class="cs218-eyebrow">Courtside · Research & evaluation</div>'
        '<h2>Model Lab</h2><p>Track validated pre-tip predictions, '
        'review model performance, and manage experimental research.</p></div>'
    )
    with st.container(key="cs218_lab_nav"):
        from mobile_filters_v225 import compact_filters_enabled
        if compact_filters_enabled():
            selected = st.selectbox(
                "Model Lab section", SECTIONS, key="cs218_lab_section"
            )
        else:
            selected = st.segmented_control(
                "Model Lab sections", SECTIONS, key="cs218_lab_section",
                default="Overview", label_visibility="collapsed"
            )
    return selected if selected in SECTIONS else "Overview"


@dataclass
class ModelLabSnapshot:
    saved_forecasts: int
    d1_games: int
    mae: str
    winner_accuracy: str
    all_graded: int
    excluded_invalid_pre_tip: int
    monthly: pd.DataFrame
    daily: pd.DataFrame
    issues: tuple[str, ...]


def build_model_lab_snapshot(forecasts: pd.DataFrame, results: pd.DataFrame):
    """Use the *same* verified timestamp and D1 definition as V123.

    This is descriptive evaluation only, not a new model or re-scoring method.
    """
    games, invalid = _graded(results)
    issues = []
    if not games.empty and "Matchup class" not in games.columns:
        issues.append("Matchup classifications are missing; D1 accuracy is not reported.")
        d1 = pd.DataFrame()
    elif games.empty:
        d1 = pd.DataFrame()
    else:
        d1 = games.loc[games["Matchup class"].eq("D1 vs D1")].copy()

    score = _score(d1)
    monthly = pd.DataFrame(columns=["Month", "Games", "MAE"])
    daily = pd.DataFrame(columns=["Game day", "Games", "MAE"])
    if not d1.empty:
        monthly = d1.groupby("Month", as_index=False).agg(
            Games=("Game ID", "size"), MAE=("Baseline error", "mean")
        )
        daily = d1.groupby("Game day", as_index=False).agg(
            Games=("Game ID", "size"), MAE=("Baseline error", "mean")
        )
    if invalid:
        issues.append(
            f"{invalid} evaluation row(s) excluded: no verified first forecast before tipoff."
        )

    return ModelLabSnapshot(
        saved_forecasts=len(forecasts),
        d1_games=int(score["Games"]),
        mae=score["MAE"],
        winner_accuracy=score["Winner accuracy"],
        all_graded=len(games),
        excluded_invalid_pre_tip=invalid,
        monthly=monthly,
        daily=daily,
        issues=tuple(issues),
    )


def render_model_lab_overview(sport: str, league: str, archived_meta):
    st.html('<div class="cs218-subhead">Season performance</div>')
    try:
        forecasts, evaluated = _read(sport)
        snapshot = build_model_lab_snapshot(forecasts, evaluated)
    except (OSError, ValueError, KeyError, TypeError, pd.errors.ParserError) as exc:
        st.warning(f"Saved performance archive could not be read: {exc}")
        return

    a, b, c, d = st.columns(4, gap="small")
    a.metric("Saved first forecasts", f"{snapshot.saved_forecasts:,}")
    b.metric("Graded D1 games", f"{snapshot.d1_games:,}")
    c.metric("Spread MAE", f"{snapshot.mae} pts" if snapshot.mae != "—" else "—")
    d.metric("Winner accuracy", snapshot.winner_accuracy)
    st.caption(
        "2026–27 baseline forecasts saved before tipoff, evaluated on completed D1 vs D1 "
        "games. MAE is average absolute error in predicted home margin. "
        "Winner accuracy excludes predicted or actual ties."
    )
    if snapshot.issues:
        for issue in snapshot.issues:
            st.warning(issue)
    if snapshot.d1_games == 0:
        st.info(
            "No eligible completed D1 games in the saved pre-tip evaluation archive yet. "
            "Accuracy and margin errors will appear when graded results are available."
        )
    else:
        chart_col, status_col = st.columns([2, 1], gap="medium")
        with chart_col:
            st.markdown("**Error over time · Completed D1 games**")
            # Data are observed grade results, not simulated trends.
            if len(snapshot.daily) >= 2:
                st.line_chart(snapshot.daily.set_index("Game day")["MAE"], y_label="Margin MAE (points)")
            else:
                st.info("At least two graded game dates are needed for a time-series chart.")
            with st.expander("Monthly performance breakdown", expanded=False):
                st.dataframe(
                    snapshot.monthly.round(2),
                    hide_index=True, use_container_width=True
                )
        with status_col:
            st.markdown("**Current rating snapshot**")
            if archived_meta:
                st.metric("Rated teams", archived_meta.get("team_count", "—"))
                st.caption(f"Rating snapshot date: {archived_meta.get('snapshot_date', 'Unknown')}")
                st.caption(
                    "Saved daily ratings are separate from the immutable pre-tip forecast archive."
                )
            else:
                st.info("No saved rating snapshot is available for this division.")
            st.metric("All graded opponent classes", snapshot.all_graded)
            st.caption("Only verified D1 vs D1 results contribute to the headline accuracy.")
    if snapshot.d1_games == 0 and archived_meta:
        st.caption(
            f"Current saved ratings: {archived_meta.get('snapshot_date','unknown date')} · "
            f"{archived_meta.get('team_count','—')} teams."
        )

    st.divider()
    st.markdown("**Explore the Model Lab**")
    col1, col2 = st.columns(2, gap="small")
    with col1:
        with st.container(border=True):
            st.markdown("**Performance**")
            st.caption(
                "Detailed game-by-game evaluation, prospective scoring, "
                "model comparisons, and historical performance trends."
            )
        with st.container(border=True):
            st.markdown("**Roster Research**")
            st.caption(
                "Archive collection, roster completeness, returning production, "
                "and experimental player features."
            )
    with col2:
        with st.container(border=True):
            st.markdown("**Predictions**")
            st.caption(
                "First forecasts, archive diagnostics, upcoming model "
                "comparisons, and immutable prediction downloads."
            )
        with st.container(border=True):
            st.markdown("**Advanced Tools**")
            st.caption(
                "Manual rating recalculation, historical backtests, "
                "and source-backed research inputs."
            )
    st.caption(
        "Choose a section above to inspect its full data. "
        "Changing the page layout does not alter Courtside's model or any archived forecasts."
    )

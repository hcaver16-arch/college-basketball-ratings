"""Courtside V212: conference comparison cards and focused conference detail tabs.

All statistics use verified D1 teams with saved ratings. Conference standings and
brackets remain provisional displays, not official seeds or tiebreakers.
"""
from __future__ import annotations

import html
import math
import re

import pandas as pd
import streamlit as st

from conference_standings import standings_for_conference
from tournament_brackets import render_tournament_bracket


COMPARE_OPTIONS = {
    "Average team power": "Average",
    "Top-five power": "Top five",
    "Median team power": "Median",
}

CONFERENCE_STYLE = """
<style>
.cs212-head{background:#fff;border:1px solid #dce6f2;border-top:4px solid #2863b4;
  border-radius:14px;padding:17px 20px;margin-bottom:13px;box-shadow:0 2px 10px rgba(26,56,96,.04)}
.cs212-kicker{color:#4073aa;font-size:.70rem;letter-spacing:.09em;font-weight:850;text-transform:uppercase}
.cs212-head h2{font-size:1.46rem;line-height:1.25;color:#173861;margin:5px 0 5px;font-weight:850}
.cs212-head p{margin:0;color:#667b96;font-size:.84rem;line-height:1.45}
.cs212-grid-top{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:9px}
.cs212-rank{font-size:.72rem;font-weight:850;background:#e6efff;color:#194a90;
  border:1px solid #d4e3fa;padding:4px 9px;border-radius:7px}
.cs212-tag{font-size:.72rem;font-weight:650;color:#68809d}
.cs212-title{color:#193c70;font-size:1.13rem;line-height:1.22;font-weight:850;
  overflow-wrap:anywhere;min-height:2.35em}
.cs212-grid-stats{display:grid;grid-template-columns:1fr 1fr;gap:9px;
  border-top:1px solid #e5ebf4;margin-top:11px;padding-top:10px}
.cs212-stat-label{font-size:.7rem;color:#788ba3;display:block;margin-bottom:2px}
.cs212-stat-value{font-size:1rem;font-weight:800;color:#203b61;font-variant-numeric:tabular-nums}
.cs212-section{font-weight:850;color:#1e406e;font-size:1.04rem;margin:15px 0 8px}
.cs212-teamline{display:flex;align-items:center;gap:11px;min-width:0;min-height:40px}
.cs212-teamline img,.cs212-table img{height:27px;width:27px;object-fit:contain;flex-shrink:0}
.cs212-team-rank{color:#577396;font-size:.84rem;font-weight:850;min-width:25px}
.cs212-team-label{font-size:.9rem;font-weight:750;color:#193c70;overflow-wrap:anywhere}
.cs212-team-sub{font-size:.73rem;color:#7185a0}
.cs212-team-power{font-size:1rem;font-weight:850;color:#194a90;text-align:right;white-space:nowrap}
.cs212-table-wrap{width:100%;overflow-x:auto;border:1px solid #dce6f2;border-radius:12px;background:white}
.cs212-table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:.85rem}
.cs212-table th{text-align:left;background:#f0f5fc;color:#426288;font-size:.74rem;
  padding:12px 10px;white-space:nowrap}
.cs212-table td{padding:10px;border-top:1px solid #e9eef6;color:#284364}
.cs212-table tbody tr:nth-child(even){background:#f8fbff}
.cs212-table .cs212-num{text-align:right;white-space:nowrap}
.cs212-table .cs212-team-name{display:flex;align-items:center;gap:8px;
  font-weight:750;color:#173b73;min-width:155px}
.cs212-table .cs212-seed{font-weight:850;color:#315fa0}
[class*="st-key-cs212_conference_"]{border:1px solid #d9e4f2!important;
  border-top:3px solid #2d65ab!important;background:#fff!important;border-radius:13px!important;
  box-shadow:0 2px 9px rgba(24,65,110,.04);padding:13px!important}
[class*="st-key-cs212_conference_"] button{font-weight:750;min-height:34px}
[class*="st-key-cs212_member_"]{background:#fff!important;border:1px solid #e1eaf4!important;
  padding:8px 12px!important;border-radius:10px!important}
@media(max-width:700px){
 .cs212-head{padding:13px 14px}.cs212-head h2{font-size:1.28rem}
 .cs212-title{font-size:1.02rem;min-height:0}
 .cs212-teamline img,.cs212-table img{height:22px;width:22px}
 .cs212-table{font-size:.77rem}.cs212-table td,.cs212-table th{padding:8px 7px}
 .cs212-table .cs212-team-name{min-width:130px}
}
</style>
"""


def _number(value, signed=True):
    try:
        value = float(value)
        return (f"{value:+.1f}" if signed else f"{value:.1f}") if math.isfinite(value) else "—"
    except (TypeError, ValueError, OverflowError):
        return "—"


def prepare_conference_summary(ratings: pd.DataFrame, verified_d1_ids: set[str]):
    """Pure data preparation; no unverified or unrated teams enter conference strength."""
    empty = pd.DataFrame(columns=["Conference", "Teams", "Average", "Median", "Top five", "Power rank"])
    required = {"Team ID", "Team", "Conference", "Current power"}
    if not isinstance(ratings, pd.DataFrame) or not required.issubset(ratings.columns) or not verified_d1_ids:
        return pd.DataFrame(), empty
    data = ratings.copy()
    data["Team ID"] = data["Team ID"].astype(str)
    data = data[data["Team ID"].isin({str(tid) for tid in verified_d1_ids})].copy()
    data["Current power"] = pd.to_numeric(data["Current power"], errors="coerce")
    data = data.dropna(subset=["Current power", "Conference", "Team"])
    data = data[~data["Conference"].astype(str).str.contains("Unassigned|not verified|Unknown", case=False, na=False)]
    data = data[data["Conference"].astype(str).str.strip().ne("")]
    data = data.drop_duplicates("Team ID")
    if data.empty:
        return data, empty
    summary = data.groupby("Conference", as_index=False).agg(
        Teams=("Team ID", "nunique"),
        Average=("Current power", "mean"),
        Median=("Current power", "median"),
    )
    top5 = data.groupby("Conference")["Current power"].apply(
        lambda values: values.nlargest(5).mean()
    ).rename("Top five").reset_index()
    summary = summary.merge(top5, on="Conference").sort_values(
        ["Average", "Conference"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)
    summary["Power rank"] = summary.index + 1
    return data, summary


def _logo(team_id: str, show_logos: bool):
    team_id = str(team_id)
    if show_logos and team_id.isdigit():
        return f'<img src="https://a.espncdn.com/i/teamlogos/ncaa/500/{team_id}.png" alt="" loading="lazy">'
    return ""


def standings_markup(standings: pd.DataFrame, show_logos=True):
    """Compact accessible standings table with escaped labels and opt-in team logos."""
    rows = []
    for seed, (_, team) in enumerate(standings.iterrows(), start=1):
        wins, losses = int(team["Conference W"]), int(team["Conference L"])
        overall = f'{int(team["Overall W"])}–{int(team["Overall L"])}'
        pct = f'{wins / (wins + losses):.3f}' if wins + losses else "—"
        tid = str(team["Team ID"])
        rows.append(
            '<tr>'
            f'<td class="cs212-seed">#{seed}</td>'
            '<td><div class="cs212-team-name">'
            f'{_logo(tid, show_logos)}{html.escape(str(team["Team"]))}</div></td>'
            f'<td class="cs212-num">{wins}–{losses}</td>'
            f'<td class="cs212-num">{pct}</td>'
            f'<td class="cs212-num">{overall}</td>'
            f'<td class="cs212-num">{html.escape(_number(team.get("Power")))}</td>'
            '</tr>'
        )
    return (
        '<div class="cs212-table-wrap"><table class="cs212-table">'
        '<thead><tr><th scope="col">Seed*</th><th scope="col">Team</th>'
        '<th scope="col" class="cs212-num">Conf.</th><th scope="col" class="cs212-num">Win %</th>'
        '<th scope="col" class="cs212-num">Overall loaded</th>'
        '<th scope="col" class="cs212-num">Power</th></tr></thead>'
        '<tbody>' + "".join(rows) + '</tbody></table></div>'
    )


def _open_team(team):
    st.session_state["courtside_requested_team"] = str(team["Team"])
    st.session_state["courtside_requested_team_id"] = str(team["Team ID"])
    st.session_state["courtside_page"] = "Teams"
    st.rerun()


def render_conferences(
    ratings: pd.DataFrame, verified_d1_ids: set[str], league: str,
    games: pd.DataFrame | None = None, coverage: str = "Selected schedule window",
):
    st.markdown(CONFERENCE_STYLE, unsafe_allow_html=True)
    if not isinstance(ratings, pd.DataFrame) or ratings.empty:
        st.info("Conference power rankings will appear once saved ratings are available.")
        return
    if not {"Team ID", "Team", "Conference", "Current power"}.issubset(ratings.columns):
        st.warning("Saved team data lacks the fields needed for conference comparisons.")
        return
    if not verified_d1_ids:
        st.warning("D1 membership unavailable; unverified conferences will not be ranked.")
        return

    data, summary = prepare_conference_summary(ratings, verified_d1_ids)
    if data.empty:
        st.info("No verified rated Division I conference members found.")
        return

    selected = st.session_state.get("cc_breakdown")
    conference_names = summary["Conference"].astype(str).tolist()
    if selected not in conference_names:
        st.session_state.pop("cc_breakdown", None)
        selected = None

    if selected:
        if st.button("← All conferences", key="cc_back_to_all"):
            st.session_state.pop("cc_breakdown", None)
            st.rerun()

        conf_row = summary.loc[summary["Conference"].astype(str).eq(selected)].iloc[0]
        st.html(
            '<div class="cs212-head"><div class="cs212-kicker">Conference center</div>'
            f'<h2>{html.escape(selected)}</h2><p>{html.escape(league)} Division I '
            '· Saved power rankings and provisional conference results</p></div>'
        )
        a, b, c, d = st.columns(4, gap="small")
        a.metric("Power rank (average)", f'#{int(conf_row["Power rank"])}')
        b.metric("Average power", _number(conf_row["Average"]))
        c.metric("Top-five power", _number(conf_row["Top five"]))
        d.metric("Rated D1 teams", int(conf_row["Teams"]))

        member = data.loc[data["Conference"].astype(str).eq(selected)].sort_values(
            ["Current power", "Team"], ascending=[False, True], kind="stable"
        )
        standings = standings_for_conference(member, games)
        tabs = st.tabs(["Standings", "Power Rankings", "Tournament"])
        with tabs[0]:
            st.caption(
                f"Completed results from {coverage}. Conference games count only current "
                "verified members. Seeds are provisional, not official tiebreak results."
            )
            if standings.empty:
                st.info("No conference teams available in the loaded data.")
            else:
                st.html(standings_markup(
                    standings, show_logos=st.session_state.get("courtside_logos_enabled", True)
                ))
                played = int((standings["Conference W"] + standings["Conference L"]).sum() / 2)
                if played == 0:
                    st.info(
                        "No completed conference games are loaded. The seed order is "
                        "an illustrative placeholder based on power rating."
                    )
                elif coverage != "Full season (Nov–Apr)":
                    st.warning(
                        "Standings use a partial schedule window. Choose Full season "
                        "(Nov–Apr) in Settings to improve coverage."
                    )
                st.caption("*Seed positions are previews only; conference-specific tie rules are not applied.")
        with tabs[1]:
            st.caption(
                "Courtside power ratings for verified conference members. "
                "These are model rankings, not official conference standings."
            )
            show_logos = st.session_state.get("courtside_logos_enabled", True)
            for ix, (_, team) in enumerate(member.iterrows(), start=1):
                with st.container(
                    key=f'cs212_member_{league}_{str(team["Team ID"])}', border=True
                ):
                    info_col, go_col = st.columns([5, 1.2], vertical_alignment="center")
                    with info_col:
                        global_rank = ""
                        if "Rank" in team and pd.notna(team["Rank"]):
                            try:
                                global_rank = f' · National #{int(team["Rank"])}'
                            except (TypeError, ValueError, OverflowError):
                                pass
                        st.html(
                            '<div class="cs212-teamline">'
                            f'<span class="cs212-team-rank">#{ix}</span>'
                            f'{_logo(team["Team ID"], show_logos)}'
                            '<div style="min-width:0;flex:1">'
                            f'<div class="cs212-team-label">{html.escape(str(team["Team"]))}</div>'
                            f'<div class="cs212-team-sub">{html.escape(global_rank.lstrip(" ·"))}</div>'
                            '</div>'
                            f'<span class="cs212-team-power">{html.escape(_number(team["Current power"]))}</span>'
                            '</div>'
                        )
                    with go_col:
                        if st.button(
                            "View team →",
                            key=f'cc_team_{league}_{team["Team ID"]}',
                            use_container_width=True,
                        ):
                            _open_team(team)
            with st.expander("Conference rating breakdown", expanded=False):
                st.metric("Median team power", _number(conf_row["Median"]))
                st.caption(
                    "Average, median, and top-five strength are computed from rated, "
                    "verified D1 members. All team power values use the saved Courtside model."
                )
        with tabs[2]:
            st.caption(
                "Tournament preview from provisional standings. Official qualification, "
                "pairings, and tiebreakers may differ; supported conference-specific formats "
                "are retained."
            )
            render_tournament_bracket(standings, selected, league)
        return

    st.html(
        '<div class="cs212-head"><div class="cs212-kicker">Courtside · Conference center</div>'
        '<h2>Conferences</h2>'
        f'<p>{html.escape(league)} Division I · Compare conference strength, '
        'then open standings, power rankings, and tournament projections.</p></div>'
    )
    search_col, sort_col, view_col = st.columns([2.4, 1.7, 1.2], gap="small")
    with search_col:
        search = st.text_input(
            "Find conference", placeholder="Search conferences…", key="cc_find"
        )
    with sort_col:
        compare_by = st.selectbox("Compare by", list(COMPARE_OPTIONS), key="cc_sort")
    with view_col:
        display_mode = st.selectbox("Display", ["Cards", "Table"], key="cs212_display")

    sort_field = COMPARE_OPTIONS[compare_by]
    shown = summary.sort_values(
        [sort_field, "Conference"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)
    # Rank is assigned before the search so a filtered conference keeps its real position.
    shown["Displayed rank"] = shown.index + 1
    if search:
        shown = shown.loc[
            shown["Conference"].astype(str).str.contains(
                search, case=False, regex=False, na=False
            )
        ]
    st.caption(
        f'{len(shown)} of {len(summary)} conferences · Ranked by {compare_by.lower()} '
        "· Saved ratings from verified D1 teams only"
    )
    if shown.empty:
        st.info("No conferences match that search.")
    elif display_mode == "Cards":
        shown = shown.reset_index(drop=True)
        for start in range(0, len(shown), 3):
            columns = st.columns(3, gap="small")
            for offset, (_, conference) in enumerate(shown.iloc[start:start + 3].iterrows()):
                with columns[offset]:
                    with st.container(
                        key=f'cs212_conference_{start + offset}', border=True
                    ):
                        rank = int(conference["Displayed rank"])
                        st.html(
                            '<div class="cs212-grid-top">'
                            f'<span class="cs212-rank">#{rank} {html.escape(compare_by)}</span>'
                            '<span class="cs212-tag">D1</span></div>'
                            f'<div class="cs212-title">{html.escape(str(conference["Conference"]))}</div>'
                            '<div class="cs212-grid-stats">'
                            '<div><span class="cs212-stat-label">Average power</span>'
                            f'<span class="cs212-stat-value">{html.escape(_number(conference["Average"]))}</span></div>'
                            '<div><span class="cs212-stat-label">Top-five power</span>'
                            f'<span class="cs212-stat-value">{html.escape(_number(conference["Top five"]))}</span></div>'
                            '<div><span class="cs212-stat-label">Median power</span>'
                            f'<span class="cs212-stat-value">{html.escape(_number(conference["Median"]))}</span></div>'
                            '<div><span class="cs212-stat-label">Rated D1 teams</span>'
                            f'<span class="cs212-stat-value">{int(conference["Teams"])}</span></div>'
                            '</div>'
                        )
                        if st.button(
                            "Explore conference →",
                            key=f'cc_open_{league}_{start + offset}',
                            use_container_width=True,
                        ):
                            st.session_state["cc_breakdown"] = str(conference["Conference"])
                            st.rerun()
    else:
        st.dataframe(
            shown[["Displayed rank", "Conference", "Teams", "Average", "Top five", "Median"]]
            .rename(columns={
                "Displayed rank": "Rank",
                "Teams": "Rated teams",
                "Average": "Average power",
                "Top five": "Top-five power",
                "Median": "Median power",
            }),
            hide_index=True, use_container_width=True
        )
        chosen = st.selectbox(
            "Open conference", shown["Conference"].astype(str).tolist(),
            key="cs212_table_pick"
        )
        if st.button("Explore conference →", key="cs212_table_open"):
            st.session_state["cc_breakdown"] = chosen
            st.rerun()

    with st.expander("How conference power is calculated · Download", expanded=False):
        st.caption(
            "An unweighted mean of saved Courtside team power ratings across verified "
            "and rated Division I conference members. Top-five is the average of the five "
            "strongest rated members (or all members when fewer than five are rated). "
            "These scores are not conference win-loss standings or official rankings."
        )
        st.download_button(
            "Download conference power rankings", summary.to_csv(index=False).encode("utf-8"),
            "courtside_conference_power.csv", "text/csv"
        )

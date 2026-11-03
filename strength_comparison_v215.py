"""Courtside V215: view SOS and SOR simultaneously, without changing the model.

Shared team and conference filters; independent SOS scope, score sorting,
pagination and CSV exports. Both panels use the verified Division I inputs
and keep provisional ranks clearly distinct from display-only positions.
"""
from __future__ import annotations

import html
import math
import pandas as pd
import streamlit as st

from strength_pages_ui import _base, _rank, _s, _navigate


STYLE_V215 = """
<style>
.cs215-header{background:#fff;border:1px solid #d9e4f2;border-top:4px solid #2864b3;
  border-radius:14px;padding:16px 19px;margin-bottom:12px}
.cs215-kicker{color:#416fa3;font-size:.72rem;font-weight:850;letter-spacing:.06em;text-transform:uppercase}
.cs215-header h2{font-weight:850;color:#1b3b67;margin:4px 0 4px;font-size:1.44rem}
.cs215-header p{font-size:.85rem;color:#647a96;margin:0}
.st-key-cs215_sos_panel,.st-key-cs215_sor_panel{
  border:1px solid #d9e5f4!important;background:#fff!important;border-radius:13px!important;
  padding:13px!important;box-shadow:0 2px 10px rgba(19,54,101,.04)}
.st-key-cs215_sos_panel{border-top:4px solid #2864b3!important}
.st-key-cs215_sor_panel{border-top:4px solid #168e83!important}
.cs215-panel-header{min-height:73px}
.cs215-panel-header h3{margin:0;font-size:1.1rem;color:#183963;font-weight:850}
.cs215-panel-header p{margin:4px 0 8px;font-size:.8rem;color:#647b98;line-height:1.35}
.cs215-row{display:flex;gap:8px;align-items:center;min-width:0;width:100%;line-height:1.3}
.cs215-rank{min-width:35px;font-weight:850;font-size:.82rem;color:#265b9f;white-space:nowrap}
.cs215-row img{width:28px;height:28px;object-fit:contain;flex:0 0 28px}
.cs215-identity{min-width:0;flex:1}
.cs215-team-name{font-size:.86rem;color:#193b68;font-weight:800;overflow-wrap:anywhere}
.cs215-conference{color:#7085a0;font-size:.72rem;overflow-wrap:anywhere}
.cs215-numbers{text-align:right;min-width:60px}
.cs215-score{font-weight:850;font-size:.98rem;color:#194981;white-space:nowrap;font-variant-numeric:tabular-nums}
.cs215-note{font-size:.68rem;color:#768aa3}
.st-key-cs215_sor_panel .cs215-score{color:#087b73}
.cs216-footnote{font-size:.74rem;color:#647b96;line-height:1.4;margin-top:11px}
[class*="st-key-cs215_row_"]{border-bottom:1px solid #e7eef7;padding:3px 2px 5px}
[class*="st-key-cs215_row_"] [data-testid="stHorizontalBlock"]{align-items:center}
[class*="st-key-cs215_row_"] button{min-height:30px!important;font-size:.76rem!important;padding:3px 8px!important}
@media(max-width:750px){
 .cs215-header{padding:13px 15px}.cs215-header h2{font-size:1.25rem}
 .st-key-cs215_sos_panel,.st-key-cs215_sor_panel{padding:11px!important}
 .cs215-row img{width:23px;height:23px;flex-basis:23px}
 .cs215-rank{min-width:27px}
 .cs215-team-name{font-size:.82rem}
 .cs215-score{font-size:.92rem}
}
</style>
"""

SOS_FIELDS = [
    "SOS rank (provisional)", "Team", "Conference", "Full SOS", "Played SOS",
    "Remaining SOS", "D1 games loaded", "Rated games", "Rating coverage %",
    "Schedule coverage status", "Coverage explanation",
]
SOR_FIELDS = [
    "SOR rank (provisional)", "Team", "Conference", "Wins", "Losses",
    "SOR games", "Reference expected wins", "Wins above expected",
    "SOR score", "SOR eligibility", "SOR position (display only)",
]


def _count(value):
    try:
        if pd.isna(value):
            return "—"
        return str(int(float(value)))
    except (TypeError, ValueError, OverflowError):
        return "—"


def prepare_strength_rows(
    teams: pd.DataFrame, *, kind: str, score_col: str, sort_col: str,
    query: str = "", conference: str = "All conferences",
):
    """Filter/sort rows; display positions are calculated before shared filters."""
    if not isinstance(teams, pd.DataFrame) or teams.empty:
        return pd.DataFrame()
    if score_col not in teams.columns:
        return teams.iloc[0:0].copy()

    out = teams.copy()
    scores = pd.to_numeric(out[score_col], errors="coerce")
    if kind == "sos":
        out["_display_sos_position"] = scores.rank(method="min", ascending=False)
    elif kind == "sor":
        # This is a display-only position based on the SOR score, not a
        # provisional SOR rank. It is useful before five rated D1 games.
        out["_display_sor_position"] = scores.rank(method="min", ascending=False)
        out["SOR position (display only)"] = out["_display_sor_position"]

    if query.strip():
        out = out[out["Team"].astype(str).str.contains(
            query.strip(), case=False, regex=False, na=False
        )].copy()
    if conference != "All conferences":
        out = out[out["Conference"].eq(conference)].copy()

    if sort_col == "Team":
        return out.sort_values("Team", kind="stable").reset_index(drop=True)
    col = sort_col if sort_col in out.columns else score_col
    out["_sortvalue"] = pd.to_numeric(out[col], errors="coerce")
    return out.sort_values(
        ["_sortvalue", "Team"], ascending=[False, True],
        na_position="last", kind="stable",
    ).reset_index(drop=True).drop(columns=["_sortvalue"])


def team_card_markup(team: pd.Series, kind: str, score_col: str, show_logos: bool):
    """Safe row markup; SOR ranks are never fabricated from incomplete evidence."""
    tid = str(team["Team ID"])
    logo = (
        f'<img src="https://a.espncdn.com/i/teamlogos/ncaa/500/{tid}.png" alt="" loading="lazy">'
        if show_logos and tid.isdigit() else ""
    )
    rank_col = "SOS rank (provisional)" if kind == "sos" else "SOR rank (provisional)"
    position = _rank(team.get(rank_col))
    if kind == "sos" and position == "—":
        position = _rank(team.get("_display_sos_position"))
        detail = "Display pos."
    elif kind == "sor" and position == "—":
        score_position = _rank(team.get("_display_sor_position"))
        position = score_position + "*" if score_position != "—" else "—"
        detail = "SOR score position (display only; not an eligible rank)"
    else:
        detail = "Provisional"

    if kind == "sos":
        note = f'{_count(team.get("Rated games"))} rated games'
    else:
        note = f'{_count(team.get("SOR games"))} completed'
    score = _s(team.get(score_col), fmt=".2f" if kind == "sor" else ".1f", signed=(kind == "sos"))

    return (
        '<div class="cs215-row">'
        f'<div class="cs215-rank" title="{html.escape(detail)}">{html.escape(position)}</div>'
        f'{logo}'
        '<div class="cs215-identity">'
        f'<div class="cs215-team-name">{html.escape(str(team["Team"]))}</div>'
        f'<div class="cs215-conference">{html.escape(str(team["Conference"]))}</div>'
        '</div><div class="cs215-numbers">'
        f'<div class="cs215-score">{html.escape(score)}</div>'
        f'<div class="cs215-note">{html.escape(note)}</div>'
        '</div></div>'
    )


def _render_panel(
    base: pd.DataFrame, *, league: str, kind: str,
    score_col: str, sort_options: dict[str, str],
    query: str, conference: str,
):
    sort_label = st.selectbox(
        "Sort by", list(sort_options), key=f"cs215_{kind}_sort"
    )
    filtered = prepare_strength_rows(
        base, kind=kind, score_col=score_col, sort_col=sort_options[sort_label],
        query=query, conference=conference,
    )
    count = len(filtered)
    st.caption(f"{count:,} matching verified D1 teams")
    if filtered.empty:
        st.info("No matching teams with this metric available.")
        return

    page_size = 12
    pages = max(1, math.ceil(count / page_size))
    if pages > 1:
        page_key = f"cs215_{kind}_page"
        current = st.session_state.get(page_key, 1)
        try:
            current = int(current)
        except (ValueError, TypeError):
            current = 1
        st.session_state[page_key] = max(1, min(pages, current))
        page = st.number_input(
            "Page", min_value=1, max_value=pages, step=1,
            key=page_key
        )
    else:
        page = 1
    start = (int(page) - 1) * page_size

    show_logos = st.session_state.get("courtside_logos_enabled", True)
    for _, team in filtered.iloc[start:start + page_size].iterrows():
        with st.container(key=f'cs215_row_{kind}_{league}_{team["Team ID"]}'):
            info_col, go_col = st.columns([5.6, 1.25], gap="small", vertical_alignment="center")
            with info_col:
                st.html(team_card_markup(team, kind, score_col, show_logos))
            with go_col:
                if st.button(
                    "Open ↗", key=f'cs215_open_{kind}_{league}_{team["Team ID"]}',
                    help=f'View {team["Team"]} profile', use_container_width=True,
                ):
                    _navigate(team)
    if pages > 1:
        st.caption(f"Page {page} of {pages} · Showing {start + 1}–{min(start + page_size, count)}")

    detail_fields = SOS_FIELDS if kind == "sos" else SOR_FIELDS
    with st.expander("Detailed data and download", expanded=False):
        columns = [c for c in detail_fields if c in filtered.columns]
        st.dataframe(filtered[columns], hide_index=True, use_container_width=True)
        st.download_button(
            "Download filtered CSV", filtered[columns].to_csv(index=False).encode(),
            f'{kind}_{league.lower().replace(" ", "_")}_strength.csv',
            "text/csv", key=f"cs215_{kind}_download"
        )


def render_strength_comparison(
    sos_df: pd.DataFrame, sor_df: pd.DataFrame,
    league: str, verified_d1_ids: set[str],
):
    """Single Strength page with both independent metric lists visible together."""
    st.markdown(STYLE_V215, unsafe_allow_html=True)
    st.html(
        '<div class="cs215-header"><div class="cs215-kicker">Courtside · Team analytics</div>'
        '<h2>Strength</h2><p>Schedule Strength (SOS) and Strength of Record (SOR) '
        'side by side · Model-derived, not official NCAA rankings.</p></div>'
    )
    sos = _base(sos_df, verified_d1_ids)
    sor = _base(sor_df, verified_d1_ids)
    if sos.empty and sor.empty:
        st.info(
            "No rated Division I schedule or record strength data is available yet. "
            "These panels will populate as ratings, schedules and completed games are recorded."
        )

    all_conferences = sorted({
        conference for base in (sos, sor) if not base.empty
        for conference in base["Conference"].unique()
        if conference and conference not in ("Unassigned", "Unassigned (not verified)")
    })
    # A previously selected conference may not exist after changing divisions.
    conference_options = ["All conferences"] + all_conferences
    if st.session_state.get("cs215_shared_conference", "All conferences") not in conference_options:
        st.session_state["cs215_shared_conference"] = "All conferences"
    # Put the SOS-only scope alongside shared filters, rather than above
    # SOS rows. This gives the two ranking panels identical control heights.
    query_col, conf_col, scope_col = st.columns([2.2, 1.5, 1.3], gap="small")
    with query_col:
        query = st.text_input(
            "Search both rankings", placeholder="School or mascot…",
            key="cs215_shared_team_query"
        )
    with conf_col:
        conference = st.selectbox(
            "Conference", conference_options,
            key="cs215_shared_conference"
        )
    with scope_col:
        scope = st.selectbox(
            "SOS scope", ["Full SOS", "Played SOS", "Remaining SOS"],
            key="cs215_sos_scope",
            help="Controls the SOS list only; SOR uses completed results."
        )

    left, right = st.columns(2, gap="medium")
    with left:
        with st.container(key="cs215_sos_panel", border=True):
            st.html(
                '<div class="cs215-panel-header"><h3>Schedule Strength (SOS)</h3>'
                '<p>Difficulty of opponents across the selected D1 schedule.</p></div>'
            )
            if sos.empty:
                st.info("SOS not available yet. Full-season schedule coverage and ratings are required.")
            else:
                _render_panel(
                    sos, league=league, kind="sos", score_col=scope,
                    sort_options={
                        "Schedule difficulty": scope,
                        "D1 games loaded": "D1 games loaded",
                        "Rated games": "Rated games",
                        "Team name": "Team",
                    },
                    query=query, conference=conference,
                )
            with st.expander("What does SOS mean?", expanded=False):
                st.write(
                    "SOS ranks are provisional when qualified by coverage; otherwise "
                    "the displayed position is based on the chosen SOS score. "
                    "Display positions are not official rankings."
                )
                st.write(
                    "Full SOS averages difficulty of rated Division I opponents in the "
                    "loaded schedule; Played SOS and Remaining SOS separate finished and "
                    "unplayed games. More positive values indicate tougher opposition "
                    "in the Courtside rating system. Coverage may be incomplete."
                )

    with right:
        with st.container(key="cs215_sor_panel", border=True):
            st.html(
                '<div class="cs215-panel-header"><h3>Strength of Record (SOR)</h3>'
                '<p>How impressive a team’s results are · * indicates display-only score position.</p></div>'
            )
            if sor.empty or "SOR score" not in sor.columns:
                st.info(
                    "SOR not available yet. Completed rated D1-v-D1 games are needed; "
                    "SOR ranks remain unavailable until eligibility is established."
                )
            else:
                _render_panel(
                    sor, league=league, kind="sor", score_col="SOR score",
                    sort_options={
                        "SOR score": "SOR score",
                        "Wins above expected": "Wins above expected",
                        "Completed D1 games": "SOR games",
                        "Team name": "Team",
                    },
                    query=query, conference=conference,
                )
            with st.expander("What does SOR mean?", expanded=False):
                st.write(
                    "An asterisk after the position indicates a display-only order "
                    "by SOR score, not a provisional or official rank. Eligible "
                    "provisional ranks require at least five rated completed D1 games."
                )
                st.write(
                    "Courtside estimates how unlikely a team's win total would be for "
                    "a reference-strength D1 team facing the same rated opponents and "
                    "locations. SOR = −log10(probability); higher is stronger. "
                    "The uncertainty model is experimental and not fully calibrated."
                )

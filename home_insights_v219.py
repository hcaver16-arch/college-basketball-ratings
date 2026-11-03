"""Courtside V219: six read-only, three-column homepage insight tiles.

Sources are saved rating history, existing conference/tournament/strength
calculations, and independent published polls. No model changes.
"""
from __future__ import annotations
from dataclasses import dataclass
import html
import math
import pandas as pd
import streamlit as st

SPORTS = {"Men's": "mens-college-basketball", "Women's": "womens-college-basketball"}

STYLE = """<style>
.cs219-title{margin:21px 0 11px;display:flex;align-items:baseline;justify-content:space-between;gap:8px;flex-wrap:wrap}
.cs219-title h2{font-size:1.28rem;font-weight:850;color:#193b69;margin:0}
.cs219-title span{font-size:.77rem;color:#72859c}
.cs219-card-head{display:flex;justify-content:space-between;align-items:center;gap:6px;margin-bottom:4px}
.cs219-card-head strong{font-size:1.02rem;font-weight:850;color:#183b6c;line-height:1.2}
.cs219-card-head span{font-size:.65rem;font-weight:800;color:#3971b0;background:#eef5ff;border-radius:6px;padding:3px 6px;white-space:nowrap}
.cs219-sub{font-size:.73rem;color:#72849c;margin-bottom:10px;line-height:1.35}
.cs219-list{min-height:117px;display:flex;flex-direction:column;gap:6px}
.cs219-row{display:flex;justify-content:space-between;align-items:baseline;gap:7px;border-bottom:1px solid #edf2f8;padding-bottom:5px}
.cs219-row:last-child{border-bottom:0}
.cs219-label{font-size:.81rem;color:#234366;font-weight:750;min-width:0;overflow-wrap:anywhere}
.cs219-value{font-size:.81rem;color:#1957a0;font-weight:850;flex-shrink:0;text-align:right;font-variant-numeric:tabular-nums}
.cs219-message{font-size:.79rem;color:#687e98;line-height:1.45;padding:7px 0}
.cs219-note{font-size:.7rem;color:#75869b;min-height:2.5em;line-height:1.3;margin-top:9px}
[class*="st-key-cs219_tile_"]{border:1px solid #dee7f2!important;border-top:3px solid #2b69b9!important;background:#fff!important;border-radius:12px!important;padding:12px 13px!important;min-width:0}
[class*="st-key-cs219_tile_"] button{font-size:.77rem!important;min-height:30px!important}
.st-key-cs219_tile_conferences{border-top-color:#14877c!important}
.st-key-cs219_tile_tournament{border-top-color:#8169ba!important}
.st-key-cs219_tile_strength{border-top-color:#d18b25!important}
.st-key-cs219_tile_players{border-top-color:#7b8ca5!important}
.st-key-cs219_tile_polls{border-top-color:#af4d74!important}
@media(max-width:850px){.cs219-title h2{font-size:1.15rem}[class*="st-key-cs219_tile_"]{padding:10px!important}.cs219-card-head strong{font-size:.94rem}.cs219-list{min-height:0}.cs219-label,.cs219-value{font-size:.77rem}}
</style>"""


@dataclass(frozen=True)
class Insight:
    id: str
    title: str
    sub: str
    rows: tuple[tuple[str, str], ...] = ()
    message: str = ""
    note: str = ""
    page: str | None = None
    badge: str = ""


def _fmt(value, decimals=1, signed=False):
    try:
        x = float(value)
        if not math.isfinite(x):
            return "—"
        return f"{x:+.{decimals}f}" if signed else f"{x:.{decimals}f}"
    except (ValueError, TypeError, OverflowError):
        return "—"


def _verified(frame, ids, required):
    if not isinstance(frame, pd.DataFrame) or frame.empty or not required.issubset(frame.columns) or not ids:
        return pd.DataFrame()
    data = frame.copy()
    data["Team ID"] = data["Team ID"].astype(str)
    return data[data["Team ID"].isin({str(item) for item in ids})].drop_duplicates("Team ID")


def rating_movers(history, ids):
    """Compare the last TWO saved dates for the same D1 teams, not preseason deltas."""
    required = {"Team ID", "Team", "Snapshot date", "Current power"}
    if not isinstance(history, pd.DataFrame) or not required.issubset(history.columns) or not ids:
        return (), "Two saved daily snapshots are needed."
    data = history.copy()
    data["Team ID"] = data["Team ID"].astype(str)
    data = data[data["Team ID"].isin({str(item) for item in ids})].copy()
    data["_day"] = pd.to_datetime(data["Snapshot date"], errors="coerce")
    days = sorted(data["_day"].dropna().unique())
    if len(days) < 2:
        return (), "Waiting for a second saved rating snapshot."
    previous, latest = days[-2:]
    earlier = data[data["_day"].eq(previous)][["Team ID", "Current power"]].drop_duplicates("Team ID")
    recent = data[data["_day"].eq(latest)][["Team ID", "Team", "Current power"]].drop_duplicates("Team ID")
    joined = recent.merge(earlier, on="Team ID", suffixes=("", " previous"), validate="one_to_one")
    joined["_change"] = (pd.to_numeric(joined["Current power"], errors="coerce") -
                         pd.to_numeric(joined["Current power previous"], errors="coerce"))
    joined = joined.dropna(subset=["_change"])
    risers = joined[joined["_change"].gt(.005)].sort_values(["_change", "Team"], ascending=[False, True]).head(2)
    fallers = joined[joined["_change"].lt(-.005)].sort_values(["_change", "Team"], ascending=[True, True]).head(1)
    rows = tuple(
        ("↑ " + str(r["Team"]), _fmt(r["_change"], signed=True)) for _, r in risers.iterrows()
    ) + tuple(
        ("↓ " + str(r["Team"]), _fmt(r["_change"], signed=True)) for _, r in fallers.iterrows()
    )
    return rows, "" if rows else "No meaningful daily power-rating changes yet."


def conference_leaders(ratings, ids):
    from conferences_ui import prepare_conference_summary
    _, summary = prepare_conference_summary(ratings, ids)
    if summary.empty:
        return (), "Verified conference power data are not available."
    return tuple(
        (f'{int(r["Power rank"])}. {r["Conference"]}', _fmt(r["Average"], signed=True))
        for _, r in summary.head(3).iterrows()
    ), ""


def projected_front_runners(ratings, ids, sor):
    """Reuse the existing Tournament projection; do not invent regional seeds."""
    from bracketology_v138 import project_field
    try:
        field, problem = project_field(ratings, ids, sor)
    except (ValueError, TypeError, KeyError, IndexError):
        return (), "Projected field temporarily unavailable."
    if problem or field.empty:
        return (), "Projected field unavailable until verified conference coverage is sufficient."
    rows = field.sort_values("Overall seed list").head(4)
    return tuple(
        (f'{int(r["Overall seed list"])}. {r["Team"]}', "Overall")
        for _, r in rows.iterrows()
    ), ""


def strength_spotlight(sos, sor, ids):
    """Only scores from verified D1 teams, not made-up eligible ranks."""
    result = []
    a = _verified(sos, ids, {"Team ID", "Team", "Full SOS"})
    if not a.empty:
        a["Full SOS"] = pd.to_numeric(a["Full SOS"], errors="coerce")
        a = a.dropna(subset=["Full SOS"]).sort_values("Full SOS", ascending=False)
        if not a.empty:
            best = a.iloc[0]
            result.append((f'SOS · {best["Team"]}', _fmt(best["Full SOS"], signed=True)))
    b = _verified(sor, ids, {"Team ID", "Team", "SOR score"})
    if not b.empty:
        b["SOR score"] = pd.to_numeric(b["SOR score"], errors="coerce")
        b = b.dropna(subset=["SOR score"]).sort_values("SOR score", ascending=False)
        if not b.empty:
            best = b.iloc[0]
            n = pd.to_numeric(pd.Series([best.get("SOR games")]), errors="coerce").iloc[0]
            sample = f" · {int(n)} game(s)" if pd.notna(n) else ""
            result.append((f'SOR · {best["Team"]}', _fmt(best["SOR score"], 2) + sample))
    return tuple(result), "" if result else "No SOS or SOR scores in the loaded D1 data."


def poll_watch(polls):
    """Never replace missing AP/Coaches data with Courtside power ranks."""
    result = []
    for kind, label in (("AP Top 25", "AP"), ("Coaches Poll", "Coaches")):
        entry = polls.get(kind, {}) if isinstance(polls, dict) else {}
        data = entry.get("rows")
        if not isinstance(data, pd.DataFrame) or data.empty or not {"Rank", "Team"}.issubset(data):
            continue
        leaders = data.loc[pd.to_numeric(data["Rank"], errors="coerce").eq(1)]
        if not leaders.empty:
            result.append((f'{label} #1 · {leaders.iloc[0]["Team"]}', ""))
    return tuple(result), "" if result else "Published poll leaders are currently unavailable."


def build_insights(ratings, ids, history, sos, sor, polls):
    movers, mover_message = rating_movers(history, ids)
    conf, conf_message = conference_leaders(ratings, ids)
    field, field_message = projected_front_runners(ratings, ids, sor)
    strength, strength_message = strength_spotlight(sos, sor, ids)
    polls_rows, polls_message = poll_watch(polls)
    return (
        Insight("movers", "Biggest Movers", "Daily change in model power", movers, mover_message,
                "Compared with the previous saved day.", "Rankings"),
        Insight("conferences", "Conference Pulse", "Top conferences by average power", conf, conf_message,
                "Verified Division I ratings only.", "Conferences"),
        Insight("tournament", "Tournament Watch", "Projected field front-runners", field, field_message,
                "Hypothetical overall order, not NCAA regional No. 1 seeds.", "Tournament"),
        Insight("strength", "Strength Spotlight", "Schedule and résumé score leaders", strength, strength_message,
                "Provisional: incomplete SOS coverage or limited SOR games may affect results.", "Strength"),
        Insight("players", "Player Leaders", "Points · rebounds · assists",
                (("Points per game", "—"), ("Rebounds per game", "—"), ("Assists per game", "—")),
                "", "2026–27 national player leaders will appear after current-season box-score coverage is verified.",
                None, "Coming soon"),
        Insight("polls", "Poll Watch", "Independent published rankings", polls_rows, polls_message,
                "Officially published AP / Coaches polls, via ESPN feed.", "Rankings"),
    )


def card_html(card: Insight):
    """Always escape external team, conference, or polling source text."""
    rows = "".join(
        '<div class="cs219-row">'
        f'<span class="cs219-label">{html.escape(str(name))}</span>'
        f'<strong class="cs219-value">{html.escape(str(value))}</strong></div>'
        for name, value in card.rows
    )
    if not rows:
        rows = f'<div class="cs219-message">{html.escape(card.message)}</div>'
    badge = f'<span>{html.escape(card.badge)}</span>' if card.badge else ""
    return (
        '<div class="cs219-card">'
        f'<div class="cs219-card-head"><strong>{html.escape(card.title)}</strong>{badge}</div>'
        f'<div class="cs219-sub">{html.escape(card.sub)}</div>'
        f'<div class="cs219-list">{rows}</div>'
        f'<div class="cs219-note">{html.escape(card.note)}</div></div>'
    )


def render_home_insights(ratings, ids, league, sos=None, sor=None):
    """Append below the existing games-first home section, with native page links."""
    from saved_ratings import load_history
    from published_polls_v137 import fetch_polls

    sport = SPORTS.get(league)
    if not sport:
        return
    try:
        history = load_history(sport)
    except (OSError, ValueError, KeyError):
        history = pd.DataFrame()
    try:
        polls = fetch_polls(sport)
    except Exception:
        polls = {}
    cards = build_insights(
        ratings, ids, history,
        sos if isinstance(sos, pd.DataFrame) else pd.DataFrame(),
        sor if isinstance(sor, pd.DataFrame) else pd.DataFrame(),
        polls,
    )
    st.markdown(STYLE, unsafe_allow_html=True)
    st.html(
        '<div class="cs219-title"><h2>Around Courtside</h2>'
        '<span>Quick insights · ' + html.escape(league) + '</span></div>'
    )
    for offset in (0, 3):
        cols = st.columns(3, gap="small")
        for col, card in zip(cols, cards[offset:offset + 3]):
            with col:
                with st.container(border=True, key=f"cs219_tile_{card.id}"):
                    st.html(card_html(card))
                    if card.page and st.button(
                        f"Explore {card.page} →", key=f"cs219_open_{card.id}_{sport}",
                        use_container_width=True
                    ):
                        st.session_state["courtside_requested_page"] = card.page
                        st.rerun()

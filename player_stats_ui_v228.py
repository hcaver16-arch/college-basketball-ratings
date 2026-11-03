"""V228 Players tab and homepage leaders based ONLY on archived ESPN box scores.

Nothing on this page recalculates or modifies Courtside team ratings.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
import json

import pandas as pd

from player_stats_v228 import ROOT, DIR, PLAYER_COLS, GAMES_COLS

SPORTS = {"Men's": "mens-college-basketball", "Women's": "womens-college-basketball"}
METRICS = (
    ("Points", "PPG", "Points per game"),
    ("Rebounds", "RPG", "Rebounds per game"),
    ("Assists", "APG", "Assists per game"),
)
SORT_OPTIONS = {
    "Points per game": "PPG", "Rebounds per game": "RPG",
    "Assists per game": "APG", "Minutes per game": "MPG",
}
MAX_REPORT_AGE_HOURS = 60

CSS = """<style>
.cs228-title{margin:3px 0 2px;color:#183b68;font-size:1.52rem;font-weight:850;letter-spacing:-.02em}
.cs228-sub{font-size:.79rem;color:#6c819b;margin-bottom:14px}
[class*="st-key-cs228_leader_"]{background:#fff!important;border:1px solid #dce6f3!important;border-top:3px solid #2c69b9!important;border-radius:12px!important;padding:12px!important}
.st-key-cs228_leader_rpg{border-top-color:#14877c!important}
.st-key-cs228_leader_apg{border-top-color:#9270bf!important}
.cs228-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;margin-bottom:9px}
.cs228-head strong{color:#1c426e;font-size:.99rem}
.cs228-head span{font-size:.67rem;color:#607fa4}
.cs228-row{display:flex;justify-content:space-between;gap:9px;padding:7px 0;border-bottom:1px solid #edf1f8}
.cs228-row:last-child{border-bottom:none}
.cs228-person{font-size:.8rem;color:#22446c;font-weight:800;line-height:1.25}
.cs228-team{color:#72839a;font-size:.69rem;line-height:1.35}
.cs228-value{font-size:1.04rem;color:#215aa0;font-weight:850;white-space:nowrap;font-variant-numeric:tabular-nums}
.cs228-foot{font-size:.72rem;color:#6f8198;margin-top:7px}
@media(max-width:700px){
 .cs228-title{font-size:1.25rem}
 [class*="st-key-cs228_leader_"]{padding:10px!important}
 .cs228-person{font-size:.79rem}
}
</style>"""


def _paths(sport: str, root: Path):
    base = root / DIR
    return (base / f"{sport}_summary.json",
            base / f"{sport}_players.csv.gz",
            base / f"{sport}_games.csv.gz")


@lru_cache(maxsize=8)
def _read_players_cached(sport: str, root_text: str, signature: tuple):
    metadata, players_path, _ = _paths(sport, Path(root_text))
    if not metadata.exists() or not players_path.exists():
        return {}, pd.DataFrame(columns=PLAYER_COLS)
    try:
        report = json.loads(metadata.read_text())
        frame = pd.read_csv(players_path, dtype={"Team ID": str, "Player ID": str})
        if not set(PLAYER_COLS).issubset(frame.columns):
            return {}, pd.DataFrame(columns=PLAYER_COLS)
        if report.get("season") != "2026-27":
            return {}, pd.DataFrame(columns=PLAYER_COLS)
        return report, frame.reindex(columns=PLAYER_COLS)
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        return {}, pd.DataFrame(columns=PLAYER_COLS)


def load_players(sport: str, root: Path = ROOT):
    if sport not in SPORTS.values():
        return {}, pd.DataFrame(columns=PLAYER_COLS)
    paths = _paths(sport, root)
    signature = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None
                      for p in paths[:2])
    meta, data = _read_players_cached(sport, str(root), signature)
    return dict(meta), data.copy()


def available(report: dict, now: datetime | None = None) -> bool:
    """Only publish national-looking ranks with sufficient, recent coverage."""
    if not report.get("player_leaders_publishable") or report.get("season") != "2026-27":
        return False
    stamp = pd.to_datetime(report.get("last_collection_run_utc"),
                           utc=True, errors="coerce")
    if pd.isna(stamp):
        return False
    now = now or datetime.now(timezone.utc)
    age_hours = (now - stamp.to_pydatetime()).total_seconds() / 3600
    return -1 <= age_hours <= MAX_REPORT_AGE_HOURS


def ranked_players(data: pd.DataFrame, metric: str, min_games=1,
                   team_ids: set[str] | None = None) -> pd.DataFrame:
    if data.empty or metric not in ("PPG", "RPG", "APG", "MPG"):
        return pd.DataFrame(columns=PLAYER_COLS)
    values = data.copy()
    if team_ids is not None:
        values = values[values["Team ID"].astype(str).isin(set(map(str, team_ids)))]
    values["GP"] = pd.to_numeric(values["GP"], errors="coerce")
    values[metric] = pd.to_numeric(values[metric], errors="coerce")
    values = values[values["GP"].ge(int(min_games))].dropna(
        subset=[metric, "Player", "Team"]
    )
    values = values[values[metric].ge(0)]
    return values.sort_values(
        [metric, "GP", "Player", "Player ID"], ascending=[False, False, True, True]
    ).reset_index(drop=True)


def home_leader_rows(league: str, ids=None, root: Path = ROOT, now=None):
    """Return rows, readable fallback, note, and publication state."""
    sport = SPORTS.get(league)
    if not sport:
        return (), "Invalid basketball division.", "", False
    report, players = load_players(sport, root)
    if not available(report, now):
        if not report:
            msg = "2026–27 ESPN player box-score collection has not been published yet."
        else:
            msg = ("Player leaders are collecting verified box scores; "
                   f"{report.get('verified_d1_team_game_boxscores', 0)} of "
                   f"{report.get('discovered_d1_team_game_boxscores', 0)} "
                   "ESPN-discovered D1 team-game box scores verified.")
        return (), msg, "Current-season numbers are never estimated from missing games.", False
    rows = []
    for title, key, _ in METRICS:
        board = ranked_players(players, key, 1, ids)
        if not board.empty:
            first = board.iloc[0]
            label = f'{title} · {first["Player"]} ({first["Team"]})'
            value = f'{float(first[key]):.1f}'
            rows.append((label, value))
    note = (
        f'{float(report.get("observed_boxscore_coverage", 0)):.0%} verified of '
        f'{report.get("discovered_d1_team_game_boxscores", 0)} ESPN-discovered '
        "D1 team-game box scores · per-game samples may be small."
    )
    return tuple(rows), "" if rows else "No verified players in the selected division.", note, bool(rows)


def _conference_frame(players, team_ratings, verified_ids):
    frame = players.copy()
    if verified_ids is not None:
        frame = frame[frame["Team ID"].astype(str).isin(set(map(str, verified_ids)))]
    if isinstance(team_ratings, pd.DataFrame) and {"Team ID", "Conference"}.issubset(team_ratings.columns):
        lookup = team_ratings[["Team ID", "Conference"]].drop_duplicates("Team ID").copy()
        lookup["Team ID"] = lookup["Team ID"].astype(str)
        frame = frame.merge(lookup, on="Team ID", how="left")
    else:
        frame["Conference"] = ""
    frame["Conference"] = frame["Conference"].fillna("").astype(str)
    return frame


def _leader_card(frame, stat_key, heading, widget_key):
    import html
    import streamlit as st
    top = ranked_players(frame, stat_key, 1).head(3)
    rows = []
    for rank, (_, p) in enumerate(top.iterrows(), 1):
        rows.append(
            '<div class="cs228-row"><div>'
            f'<div class="cs228-person">{rank}. {html.escape(str(p["Player"]))}</div>'
            f'<div class="cs228-team">{html.escape(str(p["Team"]))} · {int(p["GP"])} GP</div></div>'
            f'<div class="cs228-value">{float(p[stat_key]):.1f}</div></div>'
        )
    with st.container(border=True, key=f"cs228_leader_{widget_key}"):
        st.html(
            '<div class="cs228-head">'
            f'<strong>{html.escape(heading)}</strong><span>2026–27</span></div>'
            + "".join(rows)
            + '<div class="cs228-foot">Per game · early season samples may be small</div>'
        )


def render_players(league: str, team_ratings=None, verified_ids=None):
    import streamlit as st
    from mobile_filters_v225 import compact_filters_enabled

    sport = SPORTS.get(league, "")
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<h2 class="cs228-title">Player Leaders</h2>', unsafe_allow_html=True)
    st.markdown(
        '<div class="cs228-sub">Individual points, rebounds, assists and minutes · '
        'ESPN game box scores · 2026–27</div>', unsafe_allow_html=True
    )
    report, players = load_players(sport)
    if not report:
        st.info("Player statistics are not yet collected. Run the V228 Player Box Scores workflow in GitHub Actions.")
        return

    verified_count = int(report.get("verified_d1_team_game_boxscores", 0))
    observed_count = int(report.get("discovered_d1_team_game_boxscores", 0))
    coverage = float(report.get("observed_boxscore_coverage", 0))
    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("Verified team box scores", f"{verified_count:,}")
    c2.metric("Discovered D1 team box scores", f"{observed_count:,}")
    c3.metric("Observed coverage", f"{coverage:.1%}")
    c4.metric("Players with verified games", f'{int(report.get("athletes_with_observed_games", 0)):,}')
    st.caption(
        f'Saved archive updated {str(report.get("last_collection_run_utc", "unknown"))} · '
        "Coverage uses ESPN-discovered completed D1 team-games, not an independently complete NCAA season list."
    )
    if report.get("unverified_d1_team_game_boxscores"):
        with st.expander("Unverified games / collection diagnostics"):
            st.dataframe(pd.DataFrame(report.get("unverified_examples") or []),
                         hide_index=True, use_container_width=True)

    if not available(report):
        st.warning(
            "National leaderboards are withheld until at least 30 ESPN-discovered D1 "
            "team-game box scores are checked, at least 95% are verified, and the "
            "report is recent. Missing games are never counted as zeros."
        )
        return

    data = _conference_frame(players, team_ratings, verified_ids)
    if data.empty:
        st.info("No verified Division I player rows found for this selection.")
        return
    st.caption("Only verified box-score appearances are included. Rates are provisional until players have larger samples.")
    cards = st.columns(3, gap="small")
    for col, (_, field, heading), widget_key in zip(
        cards, METRICS, ("ppg", "rpg", "apg")
    ):
        with col:
            _leader_card(data, field, heading + " per game", widget_key)

    conferences = sorted({
        x for x in data["Conference"].unique()
        if x and x not in ("Unknown", "Unassigned", "not verified")
    })
    # Archived ratings can lack conference labels. In that case, a Team
    # filter is meaningful whereas an empty Conference dropdown is not.
    by_conference = bool(conferences)
    filter_title = "Conference" if by_conference else "Team"
    search_options = (["All conferences", *conferences] if by_conference
                      else ["All teams", *sorted(data["Team"].dropna().astype(str).unique())])
    if compact_filters_enabled():
        with st.popover("⚙ Players filters · Search, conference, minimum games", use_container_width=True):
            query = st.text_input("Search player or team", key="cs228_player_search")
            selected_conf = st.selectbox(filter_title, search_options, key="cs228_player_conference")
            sort_by = st.selectbox("Rank by", list(SORT_OPTIONS), key="cs228_player_stat")
            min_gp = st.selectbox("Minimum games played", [1, 2, 3, 5, 10, 15, 20],
                                  key="cs228_player_min_gp")
    else:
        a, b, c, d = st.columns([2.2, 1.4, 1.35, 1.1], gap="small")
        with a:
            query = st.text_input("Search player or team", key="cs228_player_search")
        with b:
            selected_conf = st.selectbox("Conference", search_options, key="cs228_player_conference")
        with c:
            sort_by = st.selectbox("Rank by", list(SORT_OPTIONS), key="cs228_player_stat")
        with d:
            min_gp = st.selectbox("Minimum games played", [1, 2, 3, 5, 10, 15, 20],
                                  key="cs228_player_min_gp")

    if selected_conf not in ("All conferences", "All teams"):
        column = "Conference" if by_conference else "Team"
        data = data.loc[data[column].eq(selected_conf)]
    if query.strip():
        term = query.strip()
        data = data[data["Player"].str.contains(term, case=False, regex=False, na=False) |
                    data["Team"].str.contains(term, case=False, regex=False, na=False)]
    metric = SORT_OPTIONS[sort_by]
    selected = ranked_players(data, metric, min_gp)
    st.caption(
        f'{len(selected):,} players · Sorted by {sort_by.lower()} · '
        f'Minimum {min_gp} verified game{"s" if min_gp != 1 else ""} · '
        "National comparability is limited by ESPN's game coverage and each athlete's sample size."
    )
    if selected.empty:
        st.info("No players match those filters or minimum-games requirement.")
        return

    table = selected[["Player", "Team", "Conference", "GP", "PPG", "RPG", "APG", "MPG"]].head(250).copy()
    table.insert(0, "Rank", range(1, len(table) + 1))
    st.dataframe(
        table, hide_index=True, use_container_width=True, height=510,
        column_config={
            "PPG": st.column_config.NumberColumn("PPG", format="%.1f"),
            "RPG": st.column_config.NumberColumn("RPG", format="%.1f"),
            "APG": st.column_config.NumberColumn("APG", format="%.1f"),
            "MPG": st.column_config.NumberColumn("MPG", format="%.1f"),
            "GP": st.column_config.NumberColumn("GP", format="%d"),
        },
    )

    # A short detail section, sourced from the archived per-game box scores.
    # We use a selectbox rather than silently assuming a row click is portable.
    options = selected.head(120)
    labels = [f'{p["Player"]} · {p["Team"]}' for _, p in options.iterrows()]
    with st.expander("Player spotlight · verified game log"):
        index = st.selectbox(
            "Player", list(range(len(options))), format_func=lambda i: labels[i],
            key="cs228_spotlight",
        )
        athlete = options.iloc[index]
        path = (ROOT / DIR / f"{sport}_games.csv.gz")
        if path.exists():
            try:
                raw = pd.read_csv(path, dtype={"Player ID": str, "Team ID": str, "Game ID": str})
                history = raw[
                    raw["Player ID"].eq(str(athlete["Player ID"])) &
                    raw["Team ID"].eq(str(athlete["Team ID"]))
                ].sort_values("Game date ET", ascending=False)
                if not history.empty:
                    st.caption(f'{athlete["Player"]} · {athlete["Team"]} · '
                               f'{len(history)} verified box score{"s" if len(history)!=1 else ""}')
                    st.dataframe(
                        history[["Game date ET", "Game ID", "Minutes", "Points", "Rebounds", "Assists"]].head(20),
                        hide_index=True, use_container_width=True,
                    )
                else:
                    st.info("Individual game history is not currently available.")
            except (OSError, KeyError, ValueError) as exc:
                st.warning(f"Archived game log unavailable: {str(exc)[:110]}")

"""V137: independent AP and Coaches college-basketball polls (display-only).

ESPN's unofficial rankings endpoint can change. Fail closed when the requested
poll is absent; never substitute Courtside power rankings for a missing poll.
"""
from __future__ import annotations
import html
import json
import re
from pathlib import Path
import pandas as pd
import requests
import streamlit as st

SPORTS = {"Men's": "mens-college-basketball", "Women's": "womens-college-basketball"}
URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/rankings"


def poll_kind(name):
    name = str(name or "").lower()
    if "associated press" in name or "ap top" in name or name.strip() == "ap":
        return "AP Top 25"
    if "coach" in name or "usa today" in name:
        return "Coaches Poll"
    return None


def _v235_record_text(value):
    """Read only genuine W-L(/T) summaries; never interpret points as a record."""
    if isinstance(value, dict):
        for key in ("summary", "displayValue", "recordSummary", "record", "overall"):
            result = _v235_record_text(value.get(key))
            if result:
                return result
        return ""
    if not isinstance(value, str):
        return ""
    text = value.strip().replace("–", "-")
    return text if re.fullmatch(r"\d+\s*-\s*\d+(?:\s*-\s*\d+)?", text) else ""


def _v235_entry_record(entry, team):
    # ESPN often attaches records to the team instead of the poll rank.
    for source in (entry, team):
        for key in ("record", "recordSummary"):
            result = _v235_record_text(source.get(key))
            if result:
                return result
    return ""


def _v235_movement(entry, current):
    """Signed places gained since the preceding published poll, if supplied."""
    raw = entry.get("previous")
    if isinstance(raw, dict):
        raw = raw.get("rank", raw.get("value"))
    try:
        prior = int(raw) if raw is not None and str(raw).strip() else None
    except (TypeError, ValueError, OverflowError):
        prior = None
    if prior is None or prior < 0:
        return "", "—"
    if prior == 0 or prior > 25:
        return "NR", "NEW"
    delta = prior - current
    return f"#{prior}", (f"▲ +{delta}" if delta > 0 else f"▼ {delta}" if delta < 0 else "— 0")


def parse_polls(payload):
    output = {}
    for item in payload.get("rankings", []):
        kind = poll_kind(item.get("name") or item.get("shortName") or item.get("abbreviation"))
        if not kind:
            continue
        rows = []
        for entry in item.get("ranks", []):
            team = entry.get("team") or {}
            if not isinstance(team, dict):
                team = {}
            raw_rank = entry.get("current", entry.get("rank"))
            try:
                rank = int(raw_rank)
            except (ValueError, TypeError):
                continue
            if not 1 <= rank <= 25:
                continue
            team_id = str(team.get("id") or entry.get("teamId") or "")
            name = team.get("displayName") or team.get("name") or entry.get("name")
            if not name:
                continue
            previous, movement = _v235_movement(entry, rank)
            rows.append({"Rank": rank, "Team": name, "Team ID": team_id,
                         "Points": entry.get("points"),
                         "Record": _v235_entry_record(entry, team),
                         "Previous poll": previous, "Movement": movement})
        if rows:
            frame = pd.DataFrame(rows).sort_values(["Rank", "Team"]).drop_duplicates("Team ID", keep="first")
            output[kind] = {"rows": frame, "date": item.get("date") or item.get("lastUpdated") or ""}
    return output


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fetch_polls(sport):
    resp = requests.get(URL.format(sport=sport), params={"groups": "50"},
                        headers={"User-Agent": "Mozilla/5.0 Courtside/1.0", "Accept": "application/json"},
                        timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        raise ValueError("Unexpected ESPN poll response")
    return parse_polls(payload)



@st.cache_data(ttl=15 * 60, show_spinner=False)
def _v235_saved_season_records(sport):
    """Read saved finals for a poll-record fallback; never fetch extra ESPN dates."""
    if sport not in SPORTS.values():
        return {}, ""
    root = Path(__file__).resolve().parent / "data" / "ratings" / sport
    archive = root / "season_2026-27.csv.gz"
    if not archive.is_file():
        return {}, ""
    needed = {"Game ID", "Date", "Status", "Home ID", "Away ID", "Home score", "Away score"}
    try:
        schedule = pd.read_csv(
            archive, compression="gzip",
            usecols=lambda column: column in needed,
            dtype={"Game ID": str, "Home ID": str, "Away ID": str},
        )
        if not needed.issubset(schedule.columns):
            return {}, ""
        schedule = schedule.drop_duplicates("Game ID", keep="last")
        from season_records import records_before_game
        # Include completed games through today, excluding future outcomes.
        today = pd.Timestamp.now(tz="America/New_York").date()
        counts = records_before_game(schedule, today + pd.Timedelta(days=1))
        record_map = {tid: f"{wins}-{losses}" for tid, (wins, losses) in counts.items()}
        as_of = ""
        status_path = root / "status.json"
        if status_path.is_file():
            as_of = str(json.loads(status_path.read_text()).get("snapshot_date") or "")
        if not as_of:
            scored = schedule[schedule["Status"].eq("Final")]
            if not scored.empty:
                as_of = str(pd.to_datetime(scored["Date"], errors="coerce").max().date())
        return record_map, as_of
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        # Record fallback is optional; missing archives must not hide polls.
        return {}, ""


def _v235_fill_missing_records(frame, sport):
    """Prefer poll-issued records; only use archived results where absent."""
    frame = frame.copy()
    missing = frame["Record"].fillna("").astype(str).str.strip().eq("")
    if not missing.any():
        return frame, 0, ""
    archived, as_of = _v235_saved_season_records(sport)
    fallback = frame["Team ID"].astype(str).map(archived)
    filled = missing & fallback.notna()
    frame.loc[filled, "Record"] = fallback.loc[filled]
    return frame, int(filled.sum()), as_of


# V196: visual parity with Courtside Power's optional ranking tiles.
POLL_TILE_STYLE = """<style>
.cr196-card{min-height:136px;color:#20385e}
.cr196-head{display:flex;justify-content:space-between;align-items:center;gap:8px}
.cr196-rank{font-size:.83rem;font-weight:850;color:#164784;background:#eaf2fc;border-radius:7px;padding:4px 8px}
.cr196-record{font-size:.75rem;color:#647993;font-weight:600}
.cr235-poll-change{font-size:.73rem;font-weight:750;margin:6px 0 1px;color:#667891}
.cr235-poll-change strong{font-variant-numeric:tabular-nums}
.cr235-poll-change.up strong{color:#168052}
.cr235-poll-change.down strong{color:#b74b42}
.cr235-poll-change.new strong{color:#1f5fb5}
.cr196-identity{display:flex;align-items:center;gap:10px;min-height:52px;margin:8px 0}
.cr196-logo{height:40px;width:40px;object-fit:contain;flex-shrink:0}
.cr196-initials{height:40px;width:40px;border-radius:9px;background:#e4edf9;color:#28518a;font-weight:800;display:grid;place-items:center;flex-shrink:0}
.cr196-name{font-size:1rem;line-height:1.22;font-weight:800;overflow-wrap:anywhere}
.cr196-metrics{border-top:1px solid #e7edf5;display:flex;justify-content:space-between;gap:8px;padding-top:9px}
.cr196-label{display:block;color:#697c97;font-size:.69rem}
.cr196-value{display:block;color:#19457f;font-size:1.13rem;font-weight:850;font-variant-numeric:tabular-nums}
.cr196-comparison{text-align:right}
[class*="st-key-cr196_poll_tiles_"] [class*="st-key-cr196_poll_card_"]{background:#fff;border:1px solid #d8e3f2;border-top:3px solid #2760b8;border-radius:12px;padding:9px 11px 8px;min-width:0}
[class*="st-key-cr196_poll_tiles_"] [class*="st-key-cr196_poll_card_"] button{min-height:30px!important;font-size:.78rem!important}
@media(max-width:700px){.cr196-logo,.cr196-initials{height:30px;width:30px}.cr196-name{font-size:.9rem}}
</style>"""


def _poll_number(value, *, prefix=""):
    """Display numeric poll/model fields without implying missing values are zero."""
    try:
        number = float(value)
        if not pd.notna(number) or not -1e9 < number < 1e9:
            return "—"
        return prefix + (str(int(number)) if number.is_integer() else f"{number:.1f}")
    except (TypeError, ValueError):
        return "—"


def _poll_tile_markup(row, *, show_logos):
    """HTML-escaped tile using published poll rank, record, and points."""
    name = str(row.get("Team", "Team"))
    tid = str(row.get("Team ID", "")).strip()
    rank = _poll_number(row.get("Rank"), prefix="#")
    record = str(row.get("Record", "")).strip()
    if record.lower() in ("nan", "none") or not record:
        record = "Record unavailable"
    points = _poll_number(row.get("Points"))
    courtside = _poll_number(row.get("Courtside rank (all rated)"), prefix="#")
    movement = str(row.get("Movement", "") or "").strip()
    if movement.lower() in ("nan", "none") or not movement:
        movement = "—"
    previous = str(row.get("Previous poll", "") or "").strip()
    if previous.lower() in ("nan", "none") or not previous:
        previous = "—"
    change_class = ("up" if movement.startswith("▲") else "down" if movement.startswith("▼")
                    else "new" if movement == "NEW" else "flat")
    change_markup = (
        '<div class="cr235-poll-change ' + change_class + '">Since last poll: '
        '<strong>' + html.escape(movement) + '</strong> · Previously '
        + html.escape(previous) + '</div>'
    )
    if show_logos and tid.isdigit():
        logo = (
            f'<img class="cr196-logo" src="https://a.espncdn.com/i/teamlogos/ncaa/500/{tid}.png" '
            'loading="lazy" alt=""/>'
        )
    else:
        initials = "".join(word[:1] for word in name.split()[:2]).upper() or "?"
        logo = '<span class="cr196-initials">' + html.escape(initials) + '</span>'
    return (
        '<div class="cr196-card">'
        '<div class="cr196-head"><span class="cr196-rank">' + html.escape(rank)
        + '</span><span class="cr196-record">' + html.escape(record) + '</span></div>'
        + change_markup +
        '<div class="cr196-identity">' + logo + '<span class="cr196-name">'
        + html.escape(name) + '</span></div>'
        '<div class="cr196-metrics"><div><span class="cr196-label">Poll points</span>'
        '<strong class="cr196-value">' + html.escape(points) + '</strong></div>'
        '<div class="cr196-comparison"><span class="cr196-label">Courtside rank</span>'
        '<strong class="cr196-value">' + html.escape(courtside) + '</strong></div></div></div>'
    )


def _open_poll_team(row):
    """Use stable ESPN IDs when navigating to a team profile."""
    team_id = str(row.get("Team ID", "")).strip()
    st.session_state["courtside_requested_team"] = str(row.get("Team", ""))
    if team_id and team_id.lower() not in ("nan", "none"):
        st.session_state["courtside_requested_team_id"] = team_id
    st.session_state["courtside_page"] = "Teams"
    st.rerun()


def render_polls(league, ratings, poll_choice=None):
    """Render a specified published poll, or keep the legacy selector when unspecified."""
    if poll_choice is None:
        st.markdown("### National polls · 2026–27")
    elif poll_choice not in ("AP Top 25", "Coaches Poll"):
        raise ValueError("Unknown published poll")
    st.caption("AP and Coaches rankings are independent published polls, not inputs to Courtside power ratings. Data: ESPN's public rankings feed (unofficial API), cached up to six hours.")
    try:
        polls = fetch_polls(SPORTS[league])
    except Exception as exc:
        st.warning(f"Poll rankings are temporarily unavailable: {exc}")
        return
    if not polls:
        st.info("No AP or Coaches poll was returned for this division. Courtside will not display unverified or previous-season ranks as current.")
        return
    choice = poll_choice if poll_choice is not None else st.radio("Poll", ["AP Top 25", "Coaches Poll"], horizontal=True, key="v137_poll")
    if choice not in polls:
        st.info(f"{choice} is not currently available from the poll source.")
        return
    record = polls[choice]
    frame = record["rows"].copy()
    date = record["date"]
    if date:
        st.caption(f"Published/updated: {date}")
    frame, saved_records_used, saved_as_of = _v235_fill_missing_records(frame, SPORTS[league])
    if saved_records_used:
        st.caption(
            f"{saved_records_used} missing poll record(s) filled from saved season finals"
            + (f" through {saved_as_of}" if saved_as_of else "")
            + ". These are Courtside results, not records frozen at the poll's publication."
        )
    st.caption("Movement compares the published rank with ESPN's previous-poll rank; — means unavailable, NEW means previously unranked.")
    if isinstance(ratings, pd.DataFrame) and not ratings.empty and {"Team ID", "Current power"}.issubset(ratings.columns):
        ranks = ratings[["Team ID", "Current power"]].copy()
        ranks["Team ID"] = ranks["Team ID"].astype(str)
        ranks["Current power"] = pd.to_numeric(ranks["Current power"], errors="coerce")
        ranks["Courtside rank (all rated)"] = ranks["Current power"].rank(ascending=False, method="min")
        frame = frame.merge(ranks[["Team ID", "Courtside rank (all rated)"]].drop_duplicates("Team ID"),
                            on="Team ID", how="left")
        st.caption("Courtside rank shown for comparison only; it ranks all rated teams, including possible non-D1 opponents.")
    # V196: both published-poll tabs have the same Tiles / Compact list options.
    # Distinct keys prevent AP and Coaches from sharing state.
    key_prefix = f"cr196_{SPORTS[league]}_{choice.lower().replace(' ', '_')}"
    mode = st.segmented_control(
        "Display rankings", ["Tiles", "Compact list"], default="Tiles",
        key=f"{key_prefix}_view",
    )
    cols = [c for c in ["Rank", "Team", "Record", "Previous poll", "Movement", "Points", "Courtside rank (all rated)"] if c in frame]
    if mode == "Compact list":
        st.dataframe(frame[cols], hide_index=True, use_container_width=True)
    else:
        st.markdown(POLL_TILE_STYLE, unsafe_allow_html=True)
        show_logos = st.session_state.get("courtside_logos_enabled", True)
        with st.container(key=f"cr196_poll_tiles_{key_prefix}"):
            for start in range(0, len(frame), 3):
                tile_cols = st.columns(3, gap="small")
                for column_index, (_, team) in enumerate(frame.iloc[start:start + 3].iterrows()):
                    position = start + column_index
                    with tile_cols[column_index]:
                        with st.container(key=f"cr196_poll_card_{key_prefix}_{position}", border=True):
                            st.html(_poll_tile_markup(team, show_logos=show_logos))
                            if st.button(
                                "View team →", key=f"{key_prefix}_team_{position}",
                                use_container_width=True,
                            ):
                                _open_poll_team(team)

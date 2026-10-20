"""College Basketball Dashboard — live schedule phase.

Uses ESPN's publicly reachable but undocumented JSON scoreboard endpoint.
Data is fetched by the deployed Streamlit server, never by the user's browser.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import io
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="College Basketball Dashboard", page_icon="🏀", layout="wide")
st.title("🏀 College Basketball Dashboard")
st.caption("2026–27 season · Real schedule feed (when available) · Power ratings coming next")

SPORTS = {"Men's": "mens-college-basketball", "Women's": "womens-college-basketball"}
START = date(2026, 11, 1)
END = date(2027, 4, 12)
COLUMNS = ["Game ID", "Date", "Time (ET)", "Away", "Home", "Away conference", "Home conference", "Venue", "Status", "Away score", "Home score", "Game URL"]


def week_ranges(start: date, end: date):
    current = start
    while current <= end:
        finish = min(current + timedelta(days=6), end)
        yield current, finish
        current = finish + timedelta(days=1)


def safe_name(team):
    return team.get("displayName") or team.get("name") or "Unknown"


def parse_game(event):
    competition = (event.get("competitions") or [{}])[0]
    participants = competition.get("competitors") or []
    home = next((c for c in participants if c.get("homeAway") == "home"), {})
    away = next((c for c in participants if c.get("homeAway") == "away"), {})
    if not home or not away:
        return None
    dt = pd.to_datetime(event.get("date"), utc=True, errors="coerce")
    if pd.isna(dt):
        return None
    local_et = dt.tz_convert("America/New_York")
    def conference(entry):
        return str((entry.get("team") or {}).get("conferenceId") or "")
    def score(entry):
        try:
            value = entry.get("score")
            if isinstance(value, dict):
                value = value.get("value") or value.get("displayValue")
            return int(float(value)) if value is not None and str(value).strip() else None
        except (ValueError, TypeError):
            return None
    status_type = (event.get("status") or {}).get("type") or {}
    if status_type.get("completed"):
        status = "Final"
    elif status_type.get("state") == "in":
        status = "Live"
    else:
        status = "Scheduled"
    is_neutral = competition.get("neutralSite") is True
    venue = "Neutral" if is_neutral else "Home"
    links = event.get("links") or competition.get("links") or []
    game_url = next((x.get("href", "") for x in links if x.get("href", "").startswith("https://")), "")
    return {"Game ID": str(event.get("id", "")), "Date": str(local_et.date()), "Time (ET)": local_et.strftime("%-I:%M %p"),
            "Away": safe_name(away.get("team") or {}), "Home": safe_name(home.get("team") or {}),
            "Away conference": conference(away), "Home conference": conference(home),
            "Venue": venue, "Status": status, "Away score": score(away) if status != "Scheduled" else None,
            "Home score": score(home) if status != "Scheduled" else None, "Game URL": game_url}


def retrieve_window(sport: str, begin: date, end: date):
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/scoreboard"
    params = {"dates": f"{begin:%Y%m%d}-{end:%Y%m%d}", "groups": "50", "limit": 500}
    response = requests.get(url, params=params, headers={"User-Agent": "CollegeBasketballScheduleDashboard/1.0"}, timeout=25)
    response.raise_for_status()
    payload = response.json()
    events = payload.get("events")
    if not isinstance(events, list):
        raise ValueError("Schedule endpoint returned no game list")
    return [parsed for event in events if (parsed := parse_game(event)) is not None], len(events)


@st.cache_data(ttl=12 * 60 * 60, show_spinner=False)
def get_schedule(sport: str, first: date, last: date):
    ranges = list(week_ranges(first, last))
    records = []
    failures = []
    potentially_truncated = []
    # A small worker pool reduces wait time without opening too many concurrent requests.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(retrieve_window, sport, a, b): (a, b) for a, b in ranges}
        for f in as_completed(futures):
            a, b = futures[f]
            try:
                rows, count = f.result()
                records.extend(rows)
                if count >= 500:
                    potentially_truncated.append(f"{a}–{b}")
            except Exception as ex:
                failures.append(f"{a}–{b}: {str(ex)[:110]}")
    result = pd.DataFrame(records, columns=COLUMNS)
    if not result.empty:
        result = result.drop_duplicates(subset=["Game ID"]).sort_values(["Date", "Time (ET)", "Away"])
    return result.reset_index(drop=True), failures, potentially_truncated, len(ranges)


def show_schedule(df):
    columns = ["Date", "Time (ET)", "Away", "Home", "Venue", "Status", "Away score", "Home score"]
    st.dataframe(df[columns], hide_index=True, use_container_width=True, height=560)


league = st.sidebar.radio("Basketball division", ["Men's", "Women's"])
st.sidebar.subheader("Season coverage")
period = st.sidebar.selectbox("Load schedules for", ["Full season (Nov–Apr)", "November–December", "January–February", "March–April"], index=0)
windows = {"Full season (Nov–Apr)": (START, END),
           "November–December": (START, date(2026, 12, 31)),
           "January–February": (date(2027, 1, 1), date(2027, 2, 28)),
           "March–April": (date(2027, 3, 1), END)}
first, last = windows[period]
st.sidebar.caption("Times shown in Eastern Time; game times and schedules may change.")
if st.sidebar.button("🔄 Refresh schedule now", use_container_width=True):
    get_schedule.clear()
    st.rerun()

st.info("Schedules are fetched from ESPN's unofficial public scoreboard feed. Game coverage depends on what ESPN has published. No ratings or point spreads are being fabricated.")

with st.spinner(f"Loading {league.lower()} games for {period.lower()}…"):
    games, failures, truncated, windows_checked = get_schedule(SPORTS[league], first, last)

if failures:
    st.warning(f"{len(failures)} of {windows_checked} weekly data requests failed. The table may be incomplete. Try refreshing later or load a shorter period.")
    with st.expander("See missing request periods"):
        st.write("\n".join(failures))
if truncated:
    st.warning("One or more date windows reached the API's 500-game cap; some games may be missing: " + ", ".join(truncated))

if games.empty:
    st.error("No schedule games could be retrieved for this selection. This can mean the feed is unavailable or schedules haven't been published. Please try a different period or refresh.")
    st.stop()

unique_teams = sorted(set(games["Away"]).union(games["Home"]))
played = int((games["Status"] == "Final").sum())
a, b, c, d = st.columns(4)
a.metric("Games retrieved", f"{len(games):,}")
b.metric("Teams appearing", f"{len(unique_teams):,}")
c.metric("Completed games", f"{played:,}")
d.metric("Scheduled games", f"{int((games['Status']=='Scheduled').sum()):,}")
st.caption("Counts describe games and teams returned by the feed, not a verified count of all Division I programs. Some non-D1 opponents may appear.")

schedule_tab, team_tab, future_tab = st.tabs(["📅 All games", "🏀 Team schedule", "📈 Ratings & lines — next phase"])
with schedule_tab:
    st.subheader(f"{league} game schedule")
    r1, r2, r3 = st.columns([2, 2, 2])
    with r1:
        team = st.selectbox("Team", ["All teams"] + unique_teams)
    with r2:
        statuses = st.multiselect("Game status", ["Scheduled", "Live", "Final"], default=["Scheduled", "Live", "Final"])
    with r3:
        venue = st.selectbox("Venue", ["All venues", "Home", "Neutral"])
    min_date = date.fromisoformat(games["Date"].min())
    max_date = date.fromisoformat(games["Date"].max())
    selected = st.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    subset = games.loc[games["Status"].isin(statuses)].copy()
    if team != "All teams":
        subset = subset.loc[(subset["Home"] == team) | (subset["Away"] == team)]
    if venue != "All venues":
        subset = subset.loc[subset["Venue"] == venue]
    if isinstance(selected, tuple) and len(selected) == 2:
        d1, d2 = selected
        subset = subset[(subset["Date"] >= str(d1)) & (subset["Date"] <= str(d2))]
    st.caption(f"Showing {len(subset):,} of {len(games):,} retrieved games")
    show_schedule(subset)
    st.download_button("Download filtered games as CSV", subset.to_csv(index=False).encode("utf-8"), file_name=f"{league.lower().replace(chr(39), '')}_basketball_games.csv", mime="text/csv")

with team_tab:
    st.subheader("Look up a team")
    chosen = st.selectbox("Select a team", unique_teams, index=0, key="individual_team")
    team_games = games.loc[(games["Away"] == chosen) | (games["Home"] == chosen)].copy()
    team_games["Opponent"] = team_games.apply(lambda r: r["Away"] if r["Home"] == chosen else r["Home"], axis=1)
    team_games["Location"] = team_games.apply(lambda r: "Neutral" if r["Venue"] == "Neutral" else ("Home" if r["Home"] == chosen else "Away"), axis=1)
    st.metric("Games currently listed", len(team_games))
    st.dataframe(team_games[["Date", "Time (ET)", "Opponent", "Location", "Status", "Away score", "Home score"]], hide_index=True, use_container_width=True)
    st.caption("This is the team schedule within the selected coverage period, not proof that all dates have been announced.")

with future_tab:
    st.subheader("Coming next: independently calculated ratings")
    st.write("Once we've checked schedule coverage, we'll add team power ratings, opponent strength, location-adjusted game lines, projected scores, and strength-of-schedule ranks. This version intentionally does not show placeholder predictions.")

st.divider()
st.caption("Data source: ESPN public scoreboard feed (unofficial/undocumented). Cached 12 hours on the server. Press Refresh schedule now to request fresh information. Source and completeness are not guaranteed.")

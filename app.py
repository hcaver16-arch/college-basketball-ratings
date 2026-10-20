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
COLUMNS = ["Game ID", "Date", "Time (ET)", "Away", "Home", "Away conference", "Home conference", "Away ID", "Home ID", "Venue", "Status", "Away score", "Home score", "Game URL"]


def days_between(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


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
            "Away ID": str((away.get("team") or {}).get("id", "")), "Home ID": str((home.get("team") or {}).get("id", "")),
            "Venue": venue, "Status": status, "Away score": score(away) if status != "Scheduled" else None,
            "Home score": score(home) if status != "Scheduled" else None, "Game URL": game_url}


@st.cache_data(ttl=12 * 60 * 60, show_spinner=False)
def retrieve_day(sport: str, day: date):
    """ESPN now rejects dates=YYYYMMDD-YYYYMMDD; use one YYYYMMDD per request."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/scoreboard"
    params = {"dates": day.strftime("%Y%m%d"), "groups": "50", "limit": 500}
    response = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0 CollegeBasketballDashboard/1.1", "Accept": "application/json"}, timeout=25)
    response.raise_for_status()
    payload = response.json()
    events = payload.get("events")
    if not isinstance(events, list):
        raise ValueError("Schedule feed did not return a game list")
    return [parsed for event in events if (parsed := parse_game(event)) is not None], len(events)


def get_schedule(sport: str, first: date, last: date):
    days = list(days_between(first, last))
    records = []
    failures = []
    possibly_truncated = []
    # Days are cached independently; switching periods reuses already fetched dates.
    # Limit parallelism to avoid overwhelming ESPN's unofficial endpoint.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(retrieve_day, sport, day): day for day in days}
        for future in as_completed(futures):
            day = futures[future]
            try:
                rows, count = future.result()
                records.extend(rows)
                if count >= 500:
                    possibly_truncated.append(str(day))
            except Exception as ex:
                failures.append(f"{day}: {str(ex)[:180]}")
    result = pd.DataFrame(records, columns=COLUMNS)
    if not result.empty:
        result = result.drop_duplicates(subset=["Game ID"]).sort_values(["Date", "Game ID"])
    return result.reset_index(drop=True), sorted(failures), sorted(possibly_truncated), len(days)



@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def fetch_directory(sport: str):
    """Team directory, separate from the schedule. Not guaranteed to include every D1 program."""
    base = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}"
    resp = requests.get(base + "/teams", params={"limit": 1000, "groups": "50"}, timeout=30,
                        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    resp.raise_for_status()
    data = resp.json()
    blocks = (data.get("sports") or [{}])[0].get("leagues") or []
    teams = []
    for league_block in blocks:
        teams.extend(league_block.get("teams") or [])
    if not teams:
        teams = data.get("teams") or []
    rows = []
    for obj in teams:
        t = obj.get("team", obj)
        if not isinstance(t, dict):
            continue
        conf = t.get("conferenceId") or (t.get("groups") or {}).get("id") if isinstance(t.get("groups"), dict) else t.get("conferenceId")
        rows.append({"Team ID": str(t.get("id", "")), "Team": t.get("displayName") or t.get("name") or "Unknown",
                     "Abbreviation": t.get("abbreviation", ""), "Conference ID": str(conf or ""),
                     "Logo": (t.get("logos") or [{}])[0].get("href", "")})
    if not rows:
        raise ValueError("ESPN returned no teams in the directory response")
    return pd.DataFrame(rows).drop_duplicates("Team ID")


@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def fetch_conference_names(sport: str):
    """Read available conference names from ESPN's groups endpoint."""
    base = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}"
    r = requests.get(base + "/groups", timeout=25,
                     headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    r.raise_for_status()
    payload = r.json()
    names = {}
    def walk(node):
        if isinstance(node, list):
            for item in node: walk(item)
        elif isinstance(node, dict):
            cid = node.get("id") or node.get("groupId")
            name = node.get("shortName") or node.get("abbreviation") or node.get("name")
            if cid is not None and name:
                names[str(cid)] = str(name)
            for field in ("groups", "children", "subGroups", "conferences", "items"):
                if field in node: walk(node[field])
    walk(payload)
    return names


def conf_label(raw: str, lookup: dict):
    if not raw or str(raw).strip() in ("", "None", "nan"):
        return "Unknown / non-D1"
    return lookup.get(str(raw), f"Conference ID {raw}")

def show_schedule(df):
    columns = ["Date", "Time (ET)", "Away", "Home", "Venue", "Status", "Away score", "Home score"]
    st.dataframe(df[columns], hide_index=True, use_container_width=True, height=560)


league = st.sidebar.radio("Basketball division", ["Men's", "Women's"])
st.sidebar.subheader("Season coverage")
period = st.sidebar.selectbox("Load schedules for", ["Next 14 days", "November 2026", "November–December", "January–February", "March–April", "Full season (Nov–Apr)"], index=0)
today = date.today()
windows = {"Next 14 days": (max(START, today), min(END, max(START, today) + timedelta(days=13))),
           "November 2026": (START, date(2026, 11, 30)),
           "Full season (Nov–Apr)": (START, END),
           "November–December": (START, date(2026, 12, 31)),
           "January–February": (date(2027, 1, 1), date(2027, 2, 28)),
           "March–April": (date(2027, 3, 1), END)}
first, last = windows[period]
st.sidebar.caption("Times shown in Eastern Time; game times and schedules may change.")
if st.sidebar.button("🔄 Refresh schedule now", use_container_width=True):
    retrieve_day.clear()
    st.rerun()

st.info("Schedules are fetched from ESPN's unofficial public scoreboard feed. Game coverage depends on what ESPN has published. No ratings or point spreads are being fabricated.")

with st.spinner(f"Loading {league.lower()} games for {period.lower()} (daily requests)…"):
    games, failures, truncated, windows_checked = get_schedule(SPORTS[league], first, last)

if failures:
    st.warning(f"{len(failures)} of {windows_checked} daily data requests failed. The table may be incomplete. Try a shorter period or refresh later.")
    with st.expander("See failed dates"):
        st.write("\n".join(failures))
if truncated:
    st.warning("Some individual days reached the API's 500-game cap; games may be missing: " + ", ".join(truncated))

if games.empty:
    st.error("No schedule games could be retrieved for this selection. This can mean the feed is unavailable or schedules haven't been published. Please try a different period or refresh.")
    st.stop()

# Team directory and conference list are sourced independently from game schedules.
try:
    directory = fetch_directory(SPORTS[league])
    directory_error = ""
except Exception as exc:
    directory = pd.DataFrame(columns=["Team ID", "Team", "Abbreviation", "Conference ID", "Logo"])
    directory_error = str(exc)
try:
    conference_names = fetch_conference_names(SPORTS[league])
    conference_error = ""
except Exception as exc:
    conference_names = {}
    conference_error = str(exc)

# Backfill conference IDs from scheduled games if the directory doesn't include them.
if not directory.empty:
    inferred = {}
    for _, game in games.iterrows():
        for side in ("Away", "Home"):
            tid = str(game[side + " ID"])
            cid = str(game[side + " conference"])
            if tid and cid and cid not in ("None", "nan"):
                inferred[tid] = cid
    directory["Conference ID"] = directory.apply(
        lambda row: row["Conference ID"] if str(row["Conference ID"]).strip() not in ("", "None", "nan")
        else inferred.get(row["Team ID"], ""), axis=1)
    directory["Conference"] = directory["Conference ID"].map(lambda v: conf_label(v, conference_names))

for side in ("Away", "Home"):
    games[side + " conference name"] = games[side + " conference"].map(lambda c: conf_label(c, conference_names))
    if not directory.empty:
        by_id = directory.set_index("Team ID")["Conference"].to_dict()
        games[side + " conference name"] = [by_id.get(tid, name) for tid, name in zip(games[side + " ID"], games[side + " conference name"])]

unique_teams = sorted(set(games["Away"]).union(games["Home"]))
played = int((games["Status"] == "Final").sum())
a, b, c, d = st.columns(4)
a.metric("Games retrieved", f"{len(games):,}")
b.metric("Teams appearing", f"{len(unique_teams):,}")
c.metric("Completed games", f"{played:,}")
d.metric("Scheduled games", f"{int((games['Status']=='Scheduled').sum()):,}")
st.caption("Counts describe games and teams returned by the feed, not a verified count of all Division I programs. Some non-D1 opponents may appear.")

schedule_tab, team_tab, directory_tab, future_tab = st.tabs(["📅 All games", "🏀 Team schedule", "🏫 Team directory & conferences", "📈 Ratings & lines — next phase"])
with schedule_tab:
    st.subheader(f"{league} game schedule")
    r1, r2, r3, r4 = st.columns([2, 2, 2, 2])
    with r1:
        team = st.selectbox("Team", ["All teams"] + unique_teams)
    with r2:
        statuses = st.multiselect("Game status", ["Scheduled", "Live", "Final"], default=["Scheduled", "Live", "Final"])
    with r3:
        venue = st.selectbox("Venue", ["All venues", "Home", "Neutral"])
    with r4:
        available_conferences = sorted(set(games["Away conference name"]).union(games["Home conference name"]))
        selected_conf = st.selectbox("Conference (either team)", ["All conferences"] + available_conferences)
    min_date = date.fromisoformat(games["Date"].min())
    max_date = date.fromisoformat(games["Date"].max())
    selected = st.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    subset = games.loc[games["Status"].isin(statuses)].copy()
    if team != "All teams":
        subset = subset.loc[(subset["Home"] == team) | (subset["Away"] == team)]
    if venue != "All venues":
        subset = subset.loc[subset["Venue"] == venue]
    if selected_conf != "All conferences":
        subset = subset.loc[(subset["Away conference name"] == selected_conf) | (subset["Home conference name"] == selected_conf)]
    if isinstance(selected, tuple) and len(selected) == 2:
        d1, d2 = selected
        subset = subset[(subset["Date"] >= str(d1)) & (subset["Date"] <= str(d2))]
    st.caption(f"Showing {len(subset):,} of {len(games):,} retrieved games")
    show_schedule(subset)
    st.download_button("Download filtered games as CSV", subset.to_csv(index=False).encode("utf-8"), file_name=f"{league.lower().replace(chr(39), '')}_basketball_games.csv", mime="text/csv")

with team_tab:
    st.subheader("Look up a team")
    chosen = st.selectbox("Select a team", unique_teams, index=0, key="individual_team")
    matched = directory[directory["Team"] == chosen] if not directory.empty else pd.DataFrame()
    if not matched.empty:
        st.caption("Conference: " + str(matched.iloc[0]["Conference"]))
    team_games = games.loc[(games["Away"] == chosen) | (games["Home"] == chosen)].copy()
    team_games["Opponent"] = team_games.apply(lambda r: r["Away"] if r["Home"] == chosen else r["Home"], axis=1)
    team_games["Location"] = team_games.apply(lambda r: "Neutral" if r["Venue"] == "Neutral" else ("Home" if r["Home"] == chosen else "Away"), axis=1)
    st.metric("Games currently listed", len(team_games))
    st.dataframe(team_games[["Date", "Time (ET)", "Opponent", "Location", "Status", "Away score", "Home score"]], hide_index=True, use_container_width=True)
    st.caption("This is the team schedule within the selected coverage period, not proof that all dates have been announced.")

with directory_tab:
    st.subheader(f"{league} teams and conferences")
    st.caption("Teams from ESPN's team directory. Conferences reflect ESPN's available feed; unrecognized IDs remain labeled. This is not yet a verified complete official D1 membership list.")
    if directory_error:
        st.warning("The team directory could not load: " + directory_error[:230])
    if conference_error:
        st.warning("Conference names could not load; IDs will be shown instead. " + conference_error[:160])
    if directory.empty:
        st.info("The independent team directory is unavailable. Your game schedules can still work.")
    else:
        options = sorted(directory["Conference"].dropna().unique().tolist())
        cf = st.selectbox("Filter by conference", ["All conferences"] + options, key="directory_conference")
        query = st.text_input("Search teams", placeholder="Type a school or abbreviation")
        filtered = directory.copy()
        if cf != "All conferences":
            filtered = filtered[filtered["Conference"] == cf]
        if query:
            filtered = filtered[filtered["Team"].str.contains(query, case=False, na=False, regex=False) | filtered["Abbreviation"].str.contains(query, case=False, na=False, regex=False)]
        st.metric("Teams in the current directory selection", len(filtered))
        st.dataframe(filtered[["Team", "Abbreviation", "Conference", "Team ID"]].sort_values("Team"), hide_index=True, use_container_width=True, height=540)
        st.download_button("Download team directory (CSV)", directory.to_csv(index=False).encode("utf-8"), file_name=f"{SPORTS[league]}-teams-2026-27.csv", mime="text/csv")
        st.caption("Conference membership can differ by sport and season. Verify against 2026–27 conference rosters before using it for official completeness claims.")

with future_tab:
    st.subheader("Coming next: independently calculated ratings")
    st.write("Once we've checked schedule coverage, we'll add team power ratings, opponent strength, location-adjusted game lines, projected scores, and strength-of-schedule ranks. This version intentionally does not show placeholder predictions.")

st.divider()
st.caption("Data source: ESPN public scoreboard feed (unofficial/undocumented). Cached 12 hours on the server. Press Refresh schedule now to request fresh information. Source and completeness are not guaranteed.")

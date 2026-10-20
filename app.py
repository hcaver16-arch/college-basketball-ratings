"""College Basketball Dashboard — live schedule phase.

Uses ESPN's publicly reachable but undocumented JSON scoreboard endpoint.
Data is fetched by the deployed Streamlit server, never by the user's browser.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import io
from math import erf, sqrt, log10
import pandas as pd
import numpy as np
import requests
import streamlit as st
from model_testing import walk_forward_backtest
from early_season_testing import compare_early_season, historical_adjustments
from roster_tracking import audit_teams, classify_team
from returning_production import calculate_returning_production, STATS_COLUMNS
from player_stats_import import fetch_prior_stats
from transfer_tracking import identify_incoming
from league_transfer_lookup import scan_previous_rosters, match_candidates
from transfer_stats import retrieve_previous_school_stats, transfer_coverage
from roster_model import experimental_roster_signal
from roster_rating_experiment import roster_sensitivity, roster_quality
from saved_roster_data import load_saved_data, build_team_roster_view, roster_archive_summary, team_saved_analysis, archive_counts
from rating_engine import calculate_power, blending_weight, make_combined
from saved_ratings import load_ratings, load_history
from roster_validation import model_feature_table, backtest_readiness

st.set_page_config(page_title="College Basketball Dashboard", page_icon="🏀", layout="wide")
st.title("🏀 College Basketball")
st.caption("2026–27 · Games, rankings and team scouting")

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
def fetch_membership(sport: str):
    """Build a season-specific conference/team map from ESPN's core group hierarchy.

    The site's flat /teams response often omits conferenceId; assigning every
    missing ID to 'non-D1' was incorrect. Core group membership resolves it.
    """
    season = 2027  # ESPN uses ending year for the 2026–27 basketball season
    base = f"https://sports.core.api.espn.com/v2/sports/basketball/leagues/{sport}/seasons/{season}/types/2"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    session = requests.Session()
    session.headers.update(headers)
    def get_json(url):
        r = session.get(url, timeout=25)
        r.raise_for_status()
        return r.json()
    def items(url):
        result = []
        while url:
            payload = get_json(url)
            result.extend(payload.get("items", []))
            url = (payload.get("page") or {}).get("next")
        return result
    # ESPN's parent group 50 represents NCAA Division I conferences.
    refs = items(base + "/groups/50/children?limit=200")
    conference_names, team_to_conf, misses = {}, {}, []
    def fetch_group(ref):
        url = ref.get("$ref", "")
        if not url:
            return None
        group = get_json(url)
        cid = str(group.get("id", ""))
        name = group.get("shortName") or group.get("name") or group.get("abbreviation") or ("Conference " + cid)
        members = items(base + "/groups/" + cid + "/teams?limit=500")
        ids = []
        for m in members:
            endpoint = m.get("$ref", "").split("?")[0].rstrip("/")
            if endpoint:
                ids.append(endpoint.rsplit("/", 1)[-1])
        return cid, name, ids
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(fetch_group, ref): ref for ref in refs}
        for future in as_completed(futures):
            try:
                val = future.result()
                if val:
                    cid, name, ids = val
                    conference_names[cid] = name
                    for tid in ids:
                        team_to_conf[tid] = cid
            except Exception as exc:
                misses.append(str(exc)[:120])
    if not team_to_conf:
        raise ValueError("Conference membership feed returned no team memberships" + ("; " + misses[0] if misses else ""))
    return conference_names, team_to_conf, len(refs), len(misses)


def conf_label(raw: str, lookup: dict):
    if not raw or str(raw).strip() in ("", "None", "nan"):
        return "Unassigned (not verified)"
    return lookup.get(str(raw), f"Conference ID {raw}")

def show_schedule(df):
    columns = ["Date", "Time (ET)", "Away", "Home", "Venue", "Status", "Model line", "Away score", "Home score"]
    st.dataframe(df[[col for col in columns if col in df.columns]], hide_index=True, use_container_width=True, height=560)



# Roster-aware ratings. A missing player data source is NOT equivalent
# to a player with zero value. No recruiting data is manufactured.
ROSTER_COLUMNS = ["Team ID", "Player", "Roster status", "Previous minutes", "Previous points", "Impact adjustment", "Source"]

@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def fetch_roster(sport: str, team_id: str):
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/teams/{team_id}/roster"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=25)
    resp.raise_for_status()
    data = resp.json()
    athletes = data.get("athletes", [])
    if isinstance(athletes, dict):
        athletes = [a for group in athletes.values() if isinstance(group, list) for a in group]
    if not isinstance(athletes, list):
        athletes = []
    result = []
    for item in athletes:
        if not isinstance(item, dict):
            continue
        athlete = item.get("athlete", item)
        if not isinstance(athlete, dict):
            continue
        result.append({"Player": athlete.get("displayName") or athlete.get("fullName") or item.get("displayName", "Unknown"),
                       "Position": (athlete.get("position") or {}).get("abbreviation", "") if isinstance(athlete.get("position"), dict) else "",
                       "Class": athlete.get("experience", {}).get("displayValue", "") if isinstance(athlete.get("experience"), dict) else ""})
    return pd.DataFrame(result, columns=["Player", "Position", "Class"])


def roster_effects(uploaded, directory_ids: set):
    if uploaded is None:
        return {}, None, "No player-impact file uploaded; recruiting and transfers make NO numerical adjustment."
    try:
        data = pd.read_csv(uploaded, dtype={"Team ID": str})
    except Exception as ex:
        return {}, None, f"Player data could not be read: {ex}"
    missing = [c for c in ROSTER_COLUMNS if c not in data.columns]
    if missing:
        return {}, data, "Missing columns: " + ", ".join(missing)
    data["Team ID"] = data["Team ID"].astype(str).str.strip()
    data["Impact adjustment"] = pd.to_numeric(data["Impact adjustment"], errors="coerce")
    data["Previous minutes"] = pd.to_numeric(data["Previous minutes"], errors="coerce")
    data["Previous points"] = pd.to_numeric(data["Previous points"], errors="coerce")
    # Unverified inputs must be visible, not silently assigned to the model.
    approved = data[(data["Impact adjustment"].notna()) & (data["Source"].fillna("").str.strip() != "") & (data["Team ID"].isin(directory_ids))]
    # Recruiting projections should never dominate proven production: all incoming
    # freshmen collectively contribute at most +2 / -2 rating points per team.
    status = approved["Roster status"].fillna("").astype(str).str.lower().str.strip()
    is_freshman = status.str.contains(r"freshman|recruit|first.year", regex=True)
    veteran = approved.loc[~is_freshman].groupby("Team ID")["Impact adjustment"].sum()
    recruits = approved.loc[is_freshman].groupby("Team ID")["Impact adjustment"].sum().clip(-2, 2)
    effects = veteran.add(recruits, fill_value=0).clip(-12, 12).to_dict()
    ignored = len(data) - len(approved)
    return effects, data, f"{len(approved)} sourced player adjustments accepted; {ignored} ignored for missing IDs, values, or sources. Incoming freshmen/recruits are capped collectively at ±2 rating points per team; all roster adjustments combined at ±12. These manually entered point impacts are assumptions, not statistically validated player projections."






def schedule_difficulty(all_games, rating_lookup, verified_d1_ids):
    """SOS only for verified D1 teams, against D1 opposition.

    All returned D1-v-D1 fixtures count toward denominator, including fixtures
    without an opponent rating; no artificial precision on sparse coverage.
    """
    all_rows, rated_rows = [], []
    for _, g in all_games.iterrows():
        home, away = str(g["Home ID"]), str(g["Away ID"])
        if home not in verified_d1_ids or away not in verified_d1_ids:
            continue
        for own, opp, side in ((home, away, "Home"), (away, home, "Away")):
            played = str(g["Status"]) == "Final"
            all_rows.append({"Team ID": own, "Played": played})
            if opp not in rating_lookup:
                continue
            is_away = str(g["Venue"]).lower() != "neutral" and side == "Away"
            is_home = str(g["Venue"]).lower() != "neutral" and side == "Home"
            difficulty = float(rating_lookup[opp]) + (3 if is_away else -3 if is_home else 0)
            rated_rows.append({"Team ID": own, "Opponent difficulty": difficulty, "Played": played})
    if not all_rows:
        return pd.DataFrame()
    all_df = pd.DataFrame(all_rows)
    rated_df = pd.DataFrame(rated_rows) if rated_rows else pd.DataFrame(columns=["Team ID", "Opponent difficulty", "Played"])
    summary = []
    for tid, group in all_df.groupby("Team ID"):
        rg = rated_df[rated_df["Team ID"] == tid]
        completed = rg[rg["Played"]]
        remaining = rg[~rg["Played"]]
        total = len(group)
        summary.append({"Team ID":tid,
            "Full SOS":rg["Opponent difficulty"].mean() if len(rg) else np.nan,
            "Played SOS":completed["Opponent difficulty"].mean() if len(completed) else np.nan,
            "Remaining SOS":remaining["Opponent difficulty"].mean() if len(remaining) else np.nan,
            "D1 games loaded":total,"Rated games":len(rg),"Played rated games":len(completed),
            "Rating coverage %":round(100*len(rg)/total,1) if total else 0})
    return pd.DataFrame(summary)


def strength_of_record(all_games, ratings, d1_ids, baseline=0.0, margin_sd=11.0):
    """Experimental record-resume score, using exact Poisson-binomial tails.

    The reference team is rating 0 on this division's fitted point scale.
    Only completed D1-v-D1 games with actual scores and a rated opponent
    count. Each game's W probability is adjusted for home advantage.
    Correlation between game outcomes is ignored: SOR is provisional.
    """
    rows = {}
    for _, game in all_games.drop_duplicates("Game ID").iterrows():
        h, a = str(game["Home ID"]), str(game["Away ID"])
        if h not in d1_ids or a not in d1_ids or game["Status"] != "Final":
            continue
        if h not in ratings or a not in ratings:
            continue
        hs, aws = pd.to_numeric(game["Home score"], errors="coerce"), pd.to_numeric(game["Away score"], errors="coerce")
        if pd.isna(hs) or pd.isna(aws) or float(hs) == float(aws):
            continue
        neutral = str(game["Venue"]).lower() == "neutral"
        for team_id, opp_id, home in [(h,a,True),(a,h,False)]:
            advantage = 0.0 if neutral else (3.0 if home else -3.0)
            expected_margin = baseline - float(ratings[opp_id]) + advantage
            z = expected_margin / (margin_sd * sqrt(2))
            prob = min(.999, max(.001, .5*(1+erf(z))))
            won = hs > aws if home else aws > hs
            rows.setdefault(team_id, []).append((prob, int(won)))
    records=[]
    for tid, observed in rows.items():
        probs = [p for p,_ in observed]
        wins = sum(w for _,w in observed)
        # Exact P(reference >= observed wins) across unequal game probabilities.
        dist = [1.0]
        for p in probs:
            nxt = [0.0]*(len(dist)+1)
            for i, prior in enumerate(dist):
                nxt[i] += prior*(1-p)
                nxt[i+1] += prior*p
            dist=nxt
        tail = min(1.0,max(1e-15,sum(dist[wins:])))
        records.append({"Team ID":tid,"SOR games":len(observed),"Wins":wins,
                        "Losses":len(observed)-wins,"Reference expected wins":round(sum(probs),2),
                        "Wins above expected":round(wins-sum(probs),2),
                        "Record tail probability":tail,"SOR score":round(-log10(tail),3)})
    return pd.DataFrame(records)


def schedule_coverage_status(d1_count, rated_count, full_window, fetch_issue):
    """Conservative, non-certifying indicators; no assumed NCAA game quota."""
    if fetch_issue:
        return "Data retrieval incomplete", "Some dates failed or were truncated; SOS may omit games."
    if not full_window:
        return "Partial date window", "Only selected dates were requested; not a season-wide schedule."
    if d1_count == 0:
        return "No D1 games loaded", "No D1-versus-D1 fixtures found for this team."
    if d1_count < 20:
        return "Sparse schedule", "Fewer than 20 D1 games are visible; season coverage is likely incomplete."
    if d1_count < 25:
        return "Review schedule", "20–24 D1 games visible; check team schedule for missing dates."
    if rated_count < d1_count:
        return "Unrated opponents", "Some D1 opponents lack power ratings; SOS uses a subset."
    return "Substantial coverage (unverified)", "25+ rated D1 games visible; completeness cannot be confirmed from the feed alone."


def game_projection(game, ratings):
    home=ratings.get(str(game["Home ID"])); away=ratings.get(str(game["Away ID"]))
    if home is None or away is None:
        return None
    margin=home-away+(0 if game["Venue"]=="Neutral" else 3.0)
    # Preliminary point-margin win probability, not market probability.
    from math import erf, sqrt
    probability=.5*(1+erf(margin/(11.0*sqrt(2))))
    return round(margin,1),round(probability*100,1)




def attach_model_lines(frame: pd.DataFrame, rating_lookup: dict, verified_d1: set):
    """Create estimated lines only where both teams are rated and verified D1."""
    out = frame.copy()
    def get_line(row):
        if row["Status"] != "Scheduled":
            return "—"
        if str(row["Home ID"]) not in verified_d1 or str(row["Away ID"]) not in verified_d1:
            return "Not rated"
        projection = game_projection(row, rating_lookup)
        if projection is None:
            return "Not rated"
        margin, _ = projection
        favorite = row["Home"] if margin >= 0 else row["Away"]
        return f"{favorite} -{abs(margin):.1f}"
    out["Model line"] = out.apply(get_line, axis=1) if not out.empty else pd.Series(dtype=str)
    return out

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
    conference_names, memberships, conf_count, conf_failures = fetch_membership(SPORTS[league])
    conference_error = ""
except Exception as exc:
    conference_names, memberships, conf_count, conf_failures = {}, {}, 0, 0
    conference_error = str(exc)

# Membership data takes precedence over blank or stale conference IDs.
if not directory.empty:
    directory["Conference ID"] = directory.apply(
        lambda row: memberships.get(str(row["Team ID"])) or str(row["Conference ID"] or ""), axis=1)
    directory["Conference"] = directory["Conference ID"].map(lambda v: conf_label(v, conference_names))

for side in ("Away", "Home"):
    games[side + " conference name"] = [
        conf_label(memberships.get(str(tid)) or cid, conference_names)
        for tid, cid in zip(games[side + " ID"], games[side + " conference"])
    ]
    if not directory.empty:
        by_id = directory.set_index("Team ID")["Conference"].to_dict()
        games[side + " conference name"] = [
            by_id.get(str(tid), name) if by_id.get(str(tid), "Unassigned (not verified)") != "Unassigned (not verified)" else name
            for tid, name in zip(games[side + " ID"], games[side + " conference name"])
        ]

if conference_error:
    st.warning("Conference membership could not be loaded: " + conference_error[:200])
else:
    st.sidebar.caption(f"Conference membership lookup: {len(memberships)} mapped teams across {len(conference_names)} conferences; {conf_failures} group lookups failed.")
if not directory.empty:
    mapped = int(directory["Team ID"].astype(str).isin(memberships).sum())
    st.sidebar.caption(f"Directory coverage: {mapped} of {len(directory)} listed teams have verified conference membership from ESPN's season group list.")

unique_teams = sorted(set(games["Away"]).union(games["Home"]))
verified_d1_ids = set(map(str, memberships.keys()))
# Start each session with the most recently archived rating snapshot.
# Manual calculations remain available, but saved ratings survive Streamlit restarts.
archived_teams, archived_meta = load_ratings(SPORTS[league])
if archived_teams is not None:
    # Saved data are authoritative until this session explicitly recalculates.
    current_snapshot = st.session_state.get(f"saved_snapshot_{SPORTS[league]}")
    archive_identity = archived_meta.get('updated_utc')
    if current_snapshot != archive_identity:
        st.session_state[f"teams_{SPORTS[league]}"] = archived_teams.copy()
        st.session_state[f"ratings_{SPORTS[league]}"] = archived_teams.set_index('Team ID')['Current power'].to_dict()
        st.session_state[f"saved_snapshot_{SPORTS[league]}"] = archive_identity
    st.sidebar.caption(f"Saved power ratings: {archived_meta.get('snapshot_date', 'unknown')} (experimental)")
else:
    st.sidebar.caption('Saved daily power ratings not collected yet; calculate in Model Lab if needed.')
ratings_for_schedule = st.session_state.get(f"ratings_{SPORTS[league]}", {})
team_ratings = st.session_state.get(f"teams_{SPORTS[league]}")
conference_ratings = st.session_state.get(f"conferences_{SPORTS[league]}")
sos_ratings = st.session_state.get(f"sos_{SPORTS[league]}")
sor_ratings = st.session_state.get(f"sor_{SPORTS[league]}")
# Summaries derived from the saved/current team rating table.
if isinstance(team_ratings, pd.DataFrame) and not team_ratings.empty:
    if 'Conference' not in team_ratings.columns and not directory.empty:
        team_ratings = team_ratings.merge(directory[['Team ID','Conference']],on='Team ID',how='left')
    if 'Conference' in team_ratings.columns:
        valid = team_ratings[team_ratings['Conference'].notna() & (team_ratings['Conference'] != 'Unassigned (not verified)')]
        if not valid.empty:
            summary = valid.groupby('Conference').agg(Teams=('Team ID','nunique'), Average_power=('Current power','mean'), Median_power=('Current power','median')).reset_index()
            best=valid.groupby('Conference')['Current power'].apply(lambda s:s.nlargest(5).mean()).rename('Top-five power').reset_index()
            conference_ratings=summary.merge(best,on='Conference').sort_values('Average_power',ascending=False)
            st.session_state[f"conferences_{SPORTS[league]}"]=conference_ratings
    if memberships and ratings_for_schedule:
        # Display a provisional SOS from the currently loaded schedule, rather than an outdated saved view.
        live_sos = schedule_difficulty(games, ratings_for_schedule, set(map(str,memberships.keys())))
        if not live_sos.empty:
            live_sos=live_sos.merge(team_ratings[['Team ID','Team','Conference']].drop_duplicates('Team ID'),on='Team ID',how='left')
            live_sos=live_sos[live_sos['Team'].notna()].copy()
            if not live_sos.empty:
                live_sos['SOS rank (provisional)']=pd.NA
                live_sos['Schedule coverage status']='Selected date window; not full-season verified'
                live_sos['Coverage explanation']='These SOS values use only currently loaded games; full-season schedule coverage has not been verified.'
                sos_ratings=live_sos
                st.session_state[f"sos_{SPORTS[league]}"]=live_sos
        live_sor = strength_of_record(games, ratings_for_schedule, set(map(str,memberships.keys())))
        if not live_sor.empty:
            live_sor=live_sor.merge(team_ratings[['Team ID','Team','Conference']].drop_duplicates('Team ID'),on='Team ID',how='left')
            live_sor['SOR rank (provisional)']=pd.NA
            sor_ratings=live_sor
            st.session_state[f"sor_{SPORTS[league]}"]=live_sor

schedule_tab, team_tab, conference_tab, sos_tab, sor_tab, ratings_tab = st.tabs(
    ["🏀 Games", "⭐ Teams", "🏆 Conferences", "📊 Schedule strength", "📈 Record strength", "⚙️ Model Lab"])

with ratings_tab:
    st.subheader("Model Lab")
    if archived_meta:
        st.success(f"Automatic ratings available: {archived_meta.get('snapshot_date')} · {archived_meta.get('team_count')} teams · {archived_meta.get('current_final_games')} current-season final games. Ratings are saved daily; manual model recalculation is optional.")
        with st.expander("Archived ratings and historical trends", expanded=False):
            st.caption("Preseason prior is based on 2025–26 scoring margins. Automatic roster bonuses are not applied; historical scale and predictive calibration remain experimental.")
            saved_history=load_history(SPORTS[league])
            if not saved_history.empty:
                st.write(f"{saved_history['Snapshot date'].nunique()} saved rating date(s)")
                st.download_button("Download all archived rating snapshots",saved_history.to_csv(index=False).encode(),f"{SPORTS[league]}_rating_history.csv","text/csv",key=f"download_hist_{SPORTS[league]}")
    else:
        st.info("No archived power ratings yet. Run the GitHub Actions 'Refresh basketball power ratings' workflow once to create the initial snapshot.")
    with st.expander("📦 Automatic roster collection progress", expanded=False):
        st.caption("Saved GitHub data are read on page load. Each nightly run processes another batch. Collection success does not prove every game or athlete was captured.")
        for division_label, division_code in [("Men", "mens-college-basketball"), ("Women", "womens-college-basketball")]:
            ap, ac, ast, alog = load_saved_data(division_code)
            counts=archive_counts(ap,ac,ast,alog)
            st.markdown(f"**{division_label}**")
            c1,c2,c3,c4=st.columns(4)
            c1.metric("Both rosters",counts['Both rosters saved'])
            c2.metric("Rosters + stats",counts['Rosters and stats saved'])
            c3.metric("Processed",counts['Collector succeeded'])
            c4.metric("Retry",counts['Needs retry'])
            st.caption("Archive status measures retrieved data, not independently verified full-season coverage.")
        st.caption("Data live in GitHub's data/ folder; scheduled GitHub Actions runs populate this archive gradually.")

    with st.expander("🔬 Roster data validation & experimental player features", expanded=False):
        st.caption("Checks the saved roster archive and calculates descriptive returning-production inputs. These are NOT trained rating adjustments.")
        pv,cv,sv,logv=load_saved_data(SPORTS[league])
        if pv.empty or cv.empty:
            st.info("Archived previous and current rosters are needed. GitHub collection is still underway.")
        else:
            feature_table=model_feature_table(pv,cv,sv,logv,calculate_returning_production)
            st.write(backtest_readiness(feature_table,"2026–27"))
            if not feature_table.empty:
                cols=['Team ID','Prior roster players','Current roster players','Prior player match %','Unmatched arrivals','Coverage status','Usable for exploratory features']
                st.dataframe(feature_table[cols],hide_index=True,use_container_width=True)
                st.download_button("Download roster validation and feature table", feature_table.to_csv(index=False).encode(),
                                   f"{SPORTS[league]}_roster_validation.csv", "text/csv", key=f"validation_download_{SPORTS[league]}")
                good=feature_table[feature_table['Usable for exploratory features']]
                if not good.empty:
                    with st.expander("Documented player-impact inputs (not fitted coefficients)"):
                        st.dataframe(good[['Team ID']+['Returning minutes % (known only)','Returning points % (known only)',
                                   'Returning rebounds % (known only)','Returning assists % (known only)']],hide_index=True,use_container_width=True)
            st.warning("Historical accuracy comparison is not yet available: current 2026–27 roster snapshots cannot be used as preseason evidence for November 2025. The existing 11.36-point November MAE remains the benchmark, not a roster-model score.")

    st.caption("Load or update ratings here. Rankings, team profiles and schedule lines appear in the other tabs after calculation.")
    st.caption("Experimental ratings based on historical scoring margins and on-court results. Player impacts are included only when supported by uploaded source-backed data; predictions are not sportsbook odds.")
    with st.expander("1. Rosters and sourced player adjustments", expanded=False):
        st.write("Choose a school to inspect its currently available ESPN roster. ESPN may not have complete 2026–27 rosters or previous-season player statistics.")
        if directory.empty:
            st.warning("Team directory unavailable; cannot select a roster.")
        else:
            school = st.selectbox("School roster", sorted(directory["Team"].unique()), key="roster_school")
            target = directory[directory["Team"] == school].iloc[0]
            if st.button("Load this roster"):
                st.session_state["roster_selected"] = (SPORTS[league], str(target["Team ID"]))
            if st.session_state.get("roster_selected") == (SPORTS[league], str(target["Team ID"])):
                try:
                    athlete_df=fetch_roster(SPORTS[league], str(target["Team ID"]))
                    if athlete_df.empty:
                        st.warning("Roster feed returned no athlete entries. No player contributions will be inferred.")
                    else:
                        st.dataframe(athlete_df, hide_index=True, use_container_width=True)
                        st.caption("Roster inclusion does not establish returning production, recruiting rank, or expected minutes.")
                except Exception as e:
                    st.warning("Roster not available from the feed: " + str(e)[:180])
        st.write("**Optional player-impact input.** Upload sourced player-level assumptions when verified stats/roster changes are available. Leave blank to use previous team performance without an invented recruiting boost.")
        st.info("Roster inputs are **manual, sourced assumptions**. ESPN roster names alone cannot establish player impact, transfer production or recruiting value. No automatic recruit ratings are inferred.")
        st.caption("Use ESPN team ID; enter the player's prior minutes and points if verified; assign a signed point-impact estimate and paste the source link. The system caps aggregate adjustments at ±12 points per team. These estimates are not yet statistically fitted.")
        sample = pd.DataFrame(columns=ROSTER_COLUMNS)
        st.download_button("Download player-input CSV template", sample.to_csv(index=False).encode(), "basketball_player_inputs.csv", "text/csv")
        uploaded_roster = st.file_uploader("Upload completed player adjustment CSV", type="csv", key="v7_roster_upload")

    with st.expander("2. Automated roster snapshot audit (experimental)", expanded=False):
        st.write("Compare ESPN's 2025–26 and 2026–27 roster listings for a small, selected set of teams. This does not automatically assign player values or presume a player transferred.")
        if directory.empty:
            st.info("Load the team directory before running an audit.")
        else:
            choices = sorted(directory["Team"].dropna().unique().tolist())
            picks = st.multiselect("Teams to check", choices, default=[], key=f"roster_audit_teams_{SPORTS[league]}")
            st.caption("Select a few teams first; ESPN requests can fail or return the same current roster for both seasons.")
            if st.button("Fetch and compare selected rosters", key=f"run_roster_audit_{SPORTS[league]}", disabled=not picks):
                chosen = directory[directory["Team"].isin(picks)]
                with st.spinner("Fetching roster snapshots for each season..."):
                    snapshots, problems = audit_teams(SPORTS[league], chosen, max_teams=len(chosen))
                st.session_state[f"roster_audit_{SPORTS[league]}"] = (snapshots, problems)
            saved = st.session_state.get(f"roster_audit_{SPORTS[league]}")
            if saved is not None:
                snapshots, problems = saved
                st.metric("Roster entries retrieved", len(snapshots))
                if not problems.empty:
                    st.warning(f"{len(problems)} season/team requests failed. Do not interpret missing players as departures.")
                    st.dataframe(problems, hide_index=True, use_container_width=True)
                summaries=[]
                for tid,group in snapshots.groupby("Team ID"):
                    old = group[group["Roster season"]==2026]; new = group[group["Roster season"]==2027]
                    unchanged = bool(not old.empty and not new.empty and set(old["Player ID"])==set(new["Player ID"]))
                    summaries.append({"Team":group["Team"].iloc[0],"2025–26 entries":len(old),"2026–27 entries":len(new),
                                      "Audit status": "Unusable: identical athlete sets" if unchanged else "Incomplete" if old.empty or new.empty else "Tentative (season validation needed)"})
                if summaries:
                    st.dataframe(pd.DataFrame(summaries),hide_index=True,use_container_width=True)
                st.download_button("Download raw roster snapshots", snapshots.to_csv(index=False).encode(),"roster_snapshots.csv","text/csv",key="download_roster_snapshots")
                st.info("Player-impact adjustments remain zero unless you upload sourced estimates. A true full-D1 transfer audit requires archived season-accurate rosters for every school and verified player IDs; this feature does not claim that coverage.")

    with st.expander("3. Returning production — sourced player statistics", expanded=False):
        st.write("Compare players listed in the two roster snapshots and calculate how much **documented 2025–26 production** appears on the 2026–27 roster.")
        st.caption("Fetch prior-season box scores automatically after auditing two roster seasons; a CSV upload remains optional. Percentages show matched known production only, not verified full-season shares, and never change power ratings.")
        st.download_button("Download stats CSV template", pd.DataFrame(columns=STATS_COLUMNS).to_csv(index=False).encode(),"prior_season_player_stats_template.csv","text/csv",key="stats_template_v17")
        audit_result=st.session_state.get(f"roster_audit_{SPORTS[league]}")
        st.markdown("**Automatic player statistics (experimental)**")
        st.caption("Fetch prior-season team game box scores from ESPN and sum player minutes, points, rebounds and assists. Start with a few teams; the source is unofficial and game coverage must be checked.")
        if st.button("Fetch 2025–26 player stats for audited teams", key=f"fetch_player_stats_{SPORTS[league]}", disabled=audit_result is None):
            chosen_ids=set(audit_result[0]["Team ID"].astype(str)) if audit_result is not None else set()
            subset=directory[directory["Team ID"].astype(str).isin(chosen_ids)][["Team ID","Team"]].drop_duplicates("Team ID").head(5)
            if subset.empty: st.warning("No audited teams to fetch. Run the roster audit first.")
            else:
                with st.spinner("Downloading historical box scores; this may take a few minutes..."):
                    data, diagnostic, failures=fetch_prior_stats(SPORTS[league],subset)
                st.session_state[f"auto_player_stats_{SPORTS[league]}"]=(data, diagnostic, failures)
        auto=st.session_state.get(f"auto_player_stats_{SPORTS[league]}")
        if auto is not None:
            data,diagnostic,failures=auto
            st.dataframe(diagnostic,hide_index=True,use_container_width=True)
            if failures: st.warning(f"{len(failures)} fetch issues. Some numbers may be incomplete; review the game coverage table.")
            if not data.empty:
                st.download_button("Download automatically retrieved player totals",data.to_csv(index=False).encode(),"player_stats_2025_26.csv","text/csv",key="auto_stats_download_v18")
        stats_upload=st.file_uploader("Optional: upload corrected/sourced 2025–26 player totals CSV",type="csv",key=f"return_stats_{SPORTS[league]}")
        audit_result=st.session_state.get(f"roster_audit_{SPORTS[league]}")
        if (stats_upload is not None or (auto is not None and not auto[0].empty)) and audit_result is not None:
            try:
                stats_data=(pd.read_csv(stats_upload,dtype={'Team ID':str,'Player ID':str}) if stats_upload is not None else auto[0])
                summary,audit,notes=calculate_returning_production(audit_result[0],stats_data)
                # Store only current division's analysis for Team Center; no effect on power ratings.
                st.session_state[f"returning_production_{SPORTS[league]}"] = (summary.copy(), audit.copy(), list(notes))
                for note in notes: st.warning(note)
                if summary.empty: st.info("No teams qualified for a returning-production calculation.")
                else:
                    st.dataframe(summary,hide_index=True,use_container_width=True)
                    st.download_button("Download returning production summary",summary.to_csv(index=False).encode(),"returning_production_summary.csv","text/csv",key="return_summary_v17")
                    with st.expander("Player-by-player reconciliation"):
                        st.dataframe(audit,hide_index=True,use_container_width=True)
                        st.download_button("Download player audit",audit.to_csv(index=False).encode(),"returning_production_player_audit.csv","text/csv",key="return_audit_v17")
                st.info("These are **known-data percentages**, not verified shares of all team production. Missing historical games/players can distort totals. Roster completeness must be reconciled before using them for ratings.")
            except Exception as exc:
                st.error("Could not read or analyze the uploaded statistics: "+str(exc)[:240])
        else:
            st.info("First fetch roster snapshots in section 2, then click automatic stats fetch above (or upload a corrected CSV).")

    with st.expander("Saved roster archive coverage", expanded=False):
        old_saved,new_saved,stats_saved,archive_status=load_saved_data(SPORTS[league])
        st.write(roster_archive_summary(old_saved,new_saved,stats_saved,archive_status))
        st.caption("Run the GitHub Actions workflow 'Refresh basketball roster archive' to update batches without manually checking each team. Archived records persist in the repository and the app redeploys after each commit.")

    with st.expander("4. Incoming players & possible transfers (experimental)", expanded=False):
        st.caption("New roster appearances are not automatically transfers. Optionally scan prior-season Division I rosters to find matching ESPN player IDs; all matches remain provisional.")
        source_audit=st.session_state.get(f"roster_audit_{SPORTS[league]}")
        source_stats=st.session_state.get(f"auto_player_stats_{SPORTS[league]}")
        if source_audit is None:
            st.info("First run the roster audit in section 2 for the teams you want to examine. Include suspected prior schools to look for matching ESPN player IDs.")
        else:
            candidates, transfer_warnings=identify_incoming(source_audit[0], source_stats[0] if source_stats is not None else None)
            for note in transfer_warnings:
                if 'only covers schools' not in note: st.caption(note)
            key=f"league_roster_lookup_{SPORTS[league]}"
            if st.button("Search 2025–26 rosters across the D1 directory", key=f"league_search_btn_{SPORTS[league]}", disabled=directory.empty):
                st.info("This runs a large number of ESPN requests and can take several minutes. Results only cover teams successfully retrieved.")
                bar=st.progress(0, text="Retrieving prior-season D1 rosters")
                prior, errors, n=scan_previous_rosters(SPORTS[league],directory, progress=lambda i,total:bar.progress(i/max(total,1),text=f"Scanned {i} of {total} D1 directory teams"))
                st.session_state[key]=(prior,errors,n)
                bar.empty()
            saved_lookup=st.session_state.get(key)
            if saved_lookup is not None:
                prior,errors,n=saved_lookup
                completed=n-len(errors)
                st.caption(f"Prior-season roster coverage: {completed} of {n} directory schools returned nonempty rosters ({len(errors)} failed/empty). This does not independently establish season accuracy.")
                if not errors.empty:
                    with st.expander("Schools with unavailable historical rosters"):
                        st.dataframe(errors,hide_index=True,use_container_width=True)
                candidates=match_candidates(candidates,prior,source_stats[0] if source_stats is not None else None)
                matched=int(candidates['Status'].astype(str).str.startswith('Potential transfer').sum()) if not candidates.empty else 0
                st.metric("Possible prior-school ID matches",matched)
                st.caption("Prior-school matches are provisional. Historical statistics can be fetched separately for only the matched players' former schools.")
                stats_key=f"transfer_prior_stats_{SPORTS[league]}"
                if st.button("Fetch previous-season statistics for matched transfers", key=f"transfer_stats_btn_{SPORTS[league]}", disabled=matched==0):
                    bar2=st.progress(0,text="Downloading previous-school box scores")
                    data2,coverage2,warnings2,attempted2=retrieve_previous_school_stats(
                        SPORTS[league],candidates,
                        progress=lambda i,total:bar2.progress(i/max(total,1),text=f"Previous schools processed: {i} of {total}"))
                    bar2.empty()
                    st.session_state[stats_key]=(data2,coverage2,warnings2,attempted2)
                fetched=st.session_state.get(stats_key)
                if fetched is not None:
                    data2,coverage2,warnings2,attempted2=fetched
                    st.caption(f"Previous schools requested: {attempted2}; individual historical player totals retrieved: {len(data2)}. Only actual retrieved totals are shown.")
                    if not coverage2.empty:
                        with st.expander("Previous-school box-score coverage"):
                            st.dataframe(coverage2,hide_index=True,use_container_width=True)
                    if warnings2:
                        with st.expander("Fetch warnings"):
                            for warning in warnings2[:80]:st.caption(warning)
                    if not data2.empty:
                        # Re-match from raw candidates using the original prior-school ID lookup.
                        candidates=match_candidates(candidates,prior,data2)
                        st.download_button("Download previous-school player totals",data2.to_csv(index=False).encode(),"transfer_previous_school_stats.csv","text/csv",key=f"transfer_stats_download_{SPORTS[league]}")
                    audit2=transfer_coverage(candidates,data2,coverage2)
                    if not audit2.empty:
                        with st.expander("Matched player and statistics coverage"):
                            st.dataframe(audit2,hide_index=True,use_container_width=True)
            st.session_state[f"incoming_candidates_{SPORTS[league]}"]=candidates.copy()
            if candidates.empty:st.info("No incoming roster appearances identified for the audited teams.")
            else:
                focus=st.selectbox("View arrivals for one team", sorted(candidates['Team'].dropna().unique().tolist()), key=f"incoming_focus_{SPORTS[league]}")
                subset=candidates[candidates['Team']==focus]
                st.metric("New roster appearances requiring verification",len(subset))
                st.dataframe(subset[['Player','Prior school','Status','Previous minutes','Previous points','Previous rebounds','Previous assists']],hide_index=True,use_container_width=True)
                st.download_button("Download all audited incoming players",candidates.to_csv(index=False).encode(),"incoming_player_candidates.csv","text/csv",key=f"incoming_download_{SPORTS[league]}")
                st.warning("All incoming-player classifications are provisional. No transfer bonuses are applied to ratings or lines.")

    roster_file = st.session_state.get("v7_roster_upload")
    ids = set(directory["Team ID"].astype(str)) if not directory.empty else set()
    effects, player_table, effect_message = roster_effects(roster_file, ids)
    st.caption(effect_message)
    if player_table is not None and not player_table.empty:
        with st.expander("Player adjustments and data audit", expanded=False):
            st.dataframe(player_table, hide_index=True, use_container_width=True)
            st.caption("Verify transfers, departures, current teams, playing time and all source URLs. Rows lacking a source or numeric adjustment will not change ratings.")
            if effects:
                audit = pd.DataFrame([{"Team ID":t,"Net player adjustment":round(v,2)} for t,v in sorted(effects.items())])
                st.dataframe(audit, hide_index=True, use_container_width=True)
    if st.button("Calculate current ratings, conference strength, SOS and lines", type="primary", key="v7_calculate"):
        st.session_state[f"v7_enabled_{SPORTS[league]}"] = True
    if st.session_state.get(f"v7_enabled_{SPORTS[league]}", False):
        with st.spinner("Calculating prior-season and current-season ratings; this may take several minutes the first time..."):
            history, he, ht, hd = get_schedule(SPORTS[league], date(2025, 11, 1), date(2026, 4, 7))
            previous, previous_stats = calculate_power(history)
            current_games, ce, ct, cd = get_schedule(SPORTS[league], START, min(END, max(START, date.today())))
            this_year, current_stats = calculate_power(current_games)
        if he or ce or ht or ct:
            st.warning(f"Some date fetches were incomplete (previous season: {len(he)} failed; current: {len(ce)} failed). All ratings, rankings, and lines below may be incomplete.")
        if previous.empty:
            st.error("Insufficient historical results; not producing predictions or conference ranks.")
        else:
            combined=make_combined(previous, this_year, effects)
            if not directory.empty:
                conf_data=directory[["Team ID","Conference"]].drop_duplicates("Team ID")
                combined=combined.merge(conf_data, how="left", on="Team ID")
            else:
                combined["Conference"]="Unassigned (not verified)"
            combined["Conference"]=combined["Conference"].fillna("Unassigned (not verified)")
            combined.insert(0,"Rank",np.arange(1,len(combined)+1))
            ratings_for_schedule = combined.set_index("Team ID")["Current power"].to_dict()
            st.session_state[f"ratings_{SPORTS[league]}"] = ratings_for_schedule
            st.session_state[f"teams_{SPORTS[league]}"] = combined.copy()
            st.caption(f"Historical finals: {previous_stats['games']:,} | Current-season finals: {current_stats['games']:,} | Rated teams: {len(combined):,}. Prior rating is zero for new teams not in last season's network.")
            st.warning("CAUTION: This first version fits each season separately and centers each fitted network independently. Blended ratings and point spreads are exploratory until cross-season calibration and roster coverage are validated.")
            t1,t2,t3,t4,t5=st.tabs(["Team ratings","Conference strength","Strength of schedule","Game lines","Model evaluation"])
            with t1:
                st.dataframe(combined[["Rank","Team","Conference","Preseason rating","On-court rating","Games played","Preseason weight","Current power","Rating change"]], hide_index=True,use_container_width=True)
                st.download_button("Download team ratings", combined.to_csv(index=False).encode(),"team_ratings.csv","text/csv")
                st.caption("At 0, 5, 10, 15, 20 and 25 games, on-court weights are 0%, 35%, 65%, 85%, 95% and 100%. Recruiting inputs have no influence after 25 games.")
            with t2:
                known=combined[combined["Conference"]!="Unassigned (not verified)"]
                if known.empty:
                    st.info("No verified team-to-conference membership available.")
                else:
                    conferences=known.groupby("Conference").agg(Teams=("Team ID","nunique"),Average_power=("Current power","mean"),Median_power=("Current power","median")).reset_index()
                    top=known.groupby("Conference")["Current power"].apply(lambda x:x.nlargest(5).mean()).rename("Top-five power").reset_index()
                    conferences=conferences.merge(top,on="Conference").sort_values("Average_power",ascending=False)
                    st.session_state[f"conferences_{SPORTS[league]}"] = conferences.copy()
                    st.dataframe(conferences,hide_index=True,use_container_width=True)
                    st.download_button("Download conference ratings",conferences.to_csv(index=False).encode(),"conference_ratings.csv","text/csv")
                    st.caption("Conference averages are affected by unmodeled programs. Check team coverage before comparing conferences.")
            rating_map=combined.set_index("Team ID")["Current power"].to_dict()
            full_games=pd.concat([current_games, games],ignore_index=True).drop_duplicates("Game ID")
            # Resume SOR is distinct from the predictive power rating and from SOS.
            sor = strength_of_record(current_games, rating_map, set(map(str,memberships.keys())))
            if not sor.empty:
                sor = sor.merge(combined[["Team ID","Team","Conference"]],on="Team ID",how="left")
                sor = sor[sor["Team"].notna()].copy()
                sor["SOR eligible"] = sor["SOR games"] >= 5
                sor = sor.sort_values(["SOR eligible","SOR score"],ascending=[False,False])
                sor["SOR rank (provisional)"] = pd.NA
                eligible = sor["SOR eligible"]
                if len(eligible):
                    sor.loc[eligible.index,"SOR rank (provisional)"] = range(1,len(eligible)+1)
            st.session_state[f"sor_{SPORTS[league]}"] = sor.copy()

            with t3:
                st.subheader("Division I strength of schedule (available games)")
                if not memberships:
                    st.error("Verified 2026–27 D1 conference membership could not be loaded. SOS ranking is disabled rather than mixing non-D1 teams into the table.")
                else:
                    sos=schedule_difficulty(full_games,rating_map,set(map(str,memberships.keys())))
                    if sos.empty:
                        st.info("No verified D1-v-D1 matchups were loaded for this date window.")
                    else:
                        sos=sos.merge(combined[["Team ID","Team","Conference"]],on="Team ID",how="left")
                        sos=sos[sos["Team"].notna()].copy()
                        if sos.empty:
                            st.info("No teams have both verified membership and a current model rating.")
                        else:
                            sos["Full SOS"] = sos["Full SOS"].round(2)
                            sos["Played SOS"] = sos["Played SOS"].round(2)
                            sos["Remaining SOS"] = sos["Remaining SOS"].round(2)
                            # Completeness measures data availability, not team strength.
                            # Full-season selected + successful responses still does NOT prove schedules are final.
                            full_window = first <= START and last >= END
                            fetch_issue = bool(failures or truncated or ce or ct)
                            statuses = [schedule_coverage_status(int(row["D1 games loaded"]), int(row["Rated games"]), full_window, fetch_issue) for _,row in sos.iterrows()]
                            sos["Schedule coverage status"] = [x[0] for x in statuses]
                            sos["Coverage explanation"] = [x[1] for x in statuses]
                            sos["SOS eligible"] = ((sos["D1 games loaded"] >= 20) & (sos["Rating coverage %"] >= 90) & full_window & (not fetch_issue))
                            sos = sos.sort_values(["SOS eligible","Full SOS"],ascending=[False,False],na_position="last")
                            # Never give an authoritative rank to sparse or partially sampled schedules.
                            eligible_count = int(sos["SOS eligible"].sum())
                            sos["SOS rank (provisional)"] = pd.NA
                            if eligible_count:
                                sos.loc[sos["SOS eligible"],"SOS rank (provisional)"] = range(1,eligible_count+1)
                            st.session_state[f"sos_{SPORTS[league]}"] = sos.copy()
                            st.warning("PROVISIONAL: Schedule coverage is NOT independently verified. Rankings are shown only for teams with 20+ loaded D1 games, 90%+ rated-opponent coverage, full season selected, and no fetch failures. These thresholds are practical screening rules, not proof of completeness.")
                            a,b,c=st.columns(3)
                            a.metric("D1 teams in SOS table",len(sos))
                            b.metric("Eligible provisional rankings",eligible_count)
                            c.metric("Need review / incomplete",len(sos)-eligible_count)
                            st.dataframe(sos[["SOS rank (provisional)","Team","Conference","Schedule coverage status","D1 games loaded","Rated games","Rating coverage %","Full SOS","Played SOS","Remaining SOS","Played rated games","Coverage explanation"]],hide_index=True,use_container_width=True)
                            st.download_button("Download provisional D1 SOS with coverage",sos.to_csv(index=False).encode(),"d1_sos_v10_coverage.csv","text/csv")
                            st.caption("'D1 games loaded' counts verified D1-versus-D1 fixtures found in fetched dates, excluding non-D1 opponents. 'Rating coverage %' measures the fraction of these games with a rated opponent, not the fraction of a team's actual full schedule retrieved. Teams with unavailable schedule data may not appear at all.")
            with t4:
                projections=[]
                for _, g in games[games["Status"]=="Scheduled"].iterrows():
                    if str(g["Home ID"]) not in memberships or str(g["Away ID"]) not in memberships: continue
                    prediction=game_projection(g,rating_map)
                    if prediction is None:continue
                    margin,win=prediction
                    projections.append({"Date":g["Date"],"Away":g["Away"],"Home":g["Home"],"Venue":g["Venue"],"Home margin projection":margin,"Model favorite":g["Home"] if margin>=0 else g["Away"],"Model line":f"{abs(margin):.1f}","Home win %":win})
                if projections:
                    prediction_df=pd.DataFrame(projections)
                    st.dataframe(prediction_df,hide_index=True,use_container_width=True)
                    st.download_button("Download projected lines",prediction_df.to_csv(index=False).encode(),"model_lines.csv","text/csv")
                    st.caption("Only verified D1-v-D1 games are projected. Positive home margin = home team favored; model line is the absolute spread for the named favorite. Illustrative modeling method, not sportsbook odds. Scores/totals are not available without a separate pace model.")
                else:
                    st.info("No scheduled matchups with valid team ratings were found in this selected date window.")
            with t5:
                st.subheader("Historical, forward-only backtest")
                st.write("Test the **scoring-margin power model** against 2025–26 games it had not seen when each prediction was made. Ratings are refitted using only games before each two-week test period; this avoids in-sample evaluation.")
                st.info("This test does **not yet measure whether roster adjustments or recruiting improve forecasts**: verified archived preseason rosters and player impacts are not available in this version. Historical final results may also be incomplete.")
                if he or ht:
                    st.warning(f"Historical source incomplete: {len(he)} failed day requests, {len(ht)} potentially truncated dates. Results may be biased.")
                if st.button("Run historical out-of-sample test", key=f"run_backtest_button_{SPORTS[league]}"):
                    with st.spinner("Running forward-only historical test; calculations may take a minute..."):
                        backtest_df, backtest_stats = walk_forward_backtest(history, set(map(str,memberships.keys())))
                    st.session_state[f"backtest_results_{SPORTS[league]}"] = (backtest_df,backtest_stats)
                saved_backtest = st.session_state.get(f"backtest_results_{SPORTS[league]}")
                if (isinstance(saved_backtest, tuple) and len(saved_backtest) == 2
                        and isinstance(saved_backtest[0], pd.DataFrame)
                        and isinstance(saved_backtest[1], dict)):
                    results, metrics = saved_backtest
                    if results.empty:
                        st.warning("Unable to score a historical test: " + metrics.get("reason", "unknown reason"))
                    else:
                        b1,b2,b3,b4 = st.columns(4)
                        b1.metric("Held-out games", f"{metrics['games_tested']:,}")
                        b2.metric("Model margin MAE", f"{metrics['MAE']:.2f} pts")
                        b3.metric("Home-only baseline MAE", f"{metrics['Baseline MAE']:.2f} pts")
                        b4.metric("Winner accuracy", f"{metrics['Win accuracy']:.1%}")
                        st.caption(f"Brier score: {metrics['Brier score']:.3f} (lower is better). {metrics['folds']} time-ordered test periods, {metrics['date_first']} to {metrics['date_last']}. This is retrospective and does not reproduce archived roster-based predictions.")
                        if metrics['MAE'] >= metrics['Baseline MAE']:
                            st.warning("The power model did not outperform a home-court-only margin baseline in this sample. Do not treat its point spreads as validated forecasts.")
                        st.dataframe(results, hide_index=True, use_container_width=True)
                        st.download_button("Download held-out game predictions", results.to_csv(index=False).encode(), f"historical_backtest_{SPORTS[league]}.csv", "text/csv")
                st.divider()
                st.subheader("November preseason-model backtest")
                with st.expander("Roster model comparison — historical readiness", expanded=False):
                    st.write("**Comparison plan:** prior-season team rating versus prior-season rating plus returning production and incoming transfers, using the **same held-out November games**.")
                    st.caption("Historical 2025–26 roster and transfer snapshots must be collected as they stood before November 2025, with 2024–25 player totals. The current 2026–27 roster scan cannot be used to evaluate November 2025 predictions.")
                    st.dataframe(pd.DataFrame([
                        {'Method':'Previous-season baseline','Historical test':'Available below','Roster evidence':'Not required'},
                        {'Method':'Returning production','Historical test':'Pending','Roster evidence':'Pre-November 2025 rosters + 2024–25 minutes'},
                        {'Method':'Incoming transfers','Historical test':'Pending','Roster evidence':'Verified former schools + 2024–25 game logs'},
                        {'Method':'Combined roster model','Historical test':'Pending','Roster evidence':'Archived and source-checked multi-season roster snapshots'}
                    ]),hide_index=True,use_container_width=True)
                    st.warning("No numeric roster-model improvement is claimed. Current team profiles show descriptive evidence only; ratings, SOS/SOR, and projected lines remain unchanged.")
                st.caption("Compare preseason predictions for November 2025 using ONLY completed 2024–25 games to fit team strength. Nov 2025 results are held out; current 2026–27 rosters are never used.")
                st.info("A proper historical roster comparison requires player changes that were known by Nov 1, 2025. This dashboard will NOT infer those values from current rosters.")
                with st.expander("Optional archived 2025–26 roster-impact CSV",expanded=False):
                    st.write("Each row requires Team ID, Impact adjustment (rating points), Source, and Known by date (YYYY-MM-DD). Historical ratings should be entered using only information publicly available by Nov 1, 2025. Total adjustment is capped to ±12 per team.")
                    template=pd.DataFrame(columns=["Team ID","Impact adjustment","Source","Known by date"])
                    st.download_button("Download historical roster template",template.to_csv(index=False).encode(),"historical_roster_template.csv","text/csv",key="early_template")
                    early_file=st.file_uploader("Upload historical roster estimates (optional)",type="csv",key=f"early_roster_{SPORTS[league]}")
                historical_effects,audit,early_note=historical_adjustments(early_file, set(map(str,memberships.keys())))
                st.caption(early_note)
                if not audit.empty:
                    with st.expander("Historical input audit"):
                        st.dataframe(audit,hide_index=True,use_container_width=True)
                if st.button("Run November 2025 preseason comparison",key=f"run_early_{SPORTS[league]}"):
                    with st.spinner("Fetching 2024–25 results and evaluating November 2025 games. Initial load may take several minutes..."):
                        early_prior, early_failed, early_trunc, _=get_schedule(SPORTS[league],date(2024,11,1),date(2025,4,8))
                        predictions, comparison, warning=compare_early_season(early_prior,history,set(map(str,memberships.keys())),historical_effects)
                    st.session_state[f"early_results_{SPORTS[league]}"]=(predictions,comparison,warning,len(early_failed),len(early_trunc))
                saved_early=st.session_state.get(f"early_results_{SPORTS[league]}")
                if isinstance(saved_early,tuple) and len(saved_early)==5:
                    early_predictions,early_metrics,early_error,early_failures,early_truncations=saved_early
                    if early_failures or early_truncations or he or ht:
                        st.warning(f"Missing or truncated source requests: prior season {early_failures+early_truncations}; test season {len(he)+len(ht)}. Results may be incomplete.")
                    if early_error:st.warning(early_error)
                    elif isinstance(early_metrics,pd.DataFrame) and not early_metrics.empty:
                        st.dataframe(early_metrics.style.format({"Margin MAE":"{:.2f}","Winner accuracy":"{:.1%}","Brier score":"{:.3f}"}),hide_index=True,use_container_width=True)
                        st.caption("Identical held-out games for all compared methods. Historical manual roster adjustments are unvalidated assumptions; improvements are descriptive, not proof of out-of-sample roster-model gains if the estimates were chosen after outcomes were known.")
                        st.download_button("Download November comparison predictions",early_predictions.to_csv(index=False).encode(),"november_2025_backtest.csv","text/csv",key="early_download")


with schedule_tab:
    st.subheader("Games & model predictions")
    st.caption("Upcoming and completed games in your selected date window. Model spreads appear after ratings are loaded in Model Lab.")
    view = st.radio("Show", ["Upcoming", "All games", "Final scores"], horizontal=True, label_visibility="collapsed")
    shown = games.copy()
    if view == "Upcoming":
        shown = shown[shown["Status"].isin(["Scheduled", "Live"])]
    elif view == "Final scores":
        shown = shown[shown["Status"] == "Final"]
    with st.expander("🔎 Filter games", expanded=False):
        f1,f2,f3=st.columns(3)
        with f1:
            team_filter=st.selectbox("Team", ["All teams"] + unique_teams, key="v12_game_team")
        with f2:
            conf_filter=st.selectbox("Conference", ["All conferences"] + sorted(set(games["Away conference name"]).union(games["Home conference name"])), key="v12_game_conf")
        with f3:
            venue_filter=st.selectbox("Venue", ["Any location", "Home", "Neutral"], key="v12_game_venue")
    if team_filter != "All teams":
        shown=shown[(shown["Home"]==team_filter)|(shown["Away"]==team_filter)]
    if conf_filter != "All conferences":
        shown=shown[(shown["Home conference name"]==conf_filter)|(shown["Away conference name"]==conf_filter)]
    if venue_filter != "Any location":
        shown=shown[shown["Venue"]==venue_filter]
    shown=attach_model_lines(shown, ratings_for_schedule, verified_d1_ids)
    st.caption(f"{len(shown):,} games shown · All times Eastern")
    if shown.empty:
        st.info("No games match this selection. Try another date window or filter.")
    else:
        st.dataframe(shown[["Date","Time (ET)","Away","Home","Status","Model line","Away score","Home score"]],
                     hide_index=True, use_container_width=True, height=470)
    with st.expander("Download games and data notes"):
        st.download_button("Download selected games CSV", shown.to_csv(index=False).encode(), "basketball_games.csv", "text/csv",key="v12_download_games")
        st.caption("ESPN schedule feed is unofficial. Projections are experimental, not sportsbook odds; unavailable estimates are shown as Not rated.")

with team_tab:
    st.subheader("Team center")
    if directory.empty:
        st.warning("The team directory is unavailable; use the Games tab until it reloads.")
    else:
        d1_teams=directory[directory["Team ID"].astype(str).isin(verified_d1_ids)].copy()
        available=d1_teams if not d1_teams.empty else directory
        team_options=sorted(available["Team"].dropna().unique())
        chosen=st.selectbox("Find a Division I team",team_options,key="v12_team_pick")
        selected_team=available[available["Team"]==chosen].iloc[0]
        tid=str(selected_team["Team ID"])
        st.caption(str(selected_team.get("Conference", "Conference unavailable")))
        row=None
        if isinstance(team_ratings,pd.DataFrame) and not team_ratings.empty:
            match=team_ratings[team_ratings["Team ID"].astype(str)==tid]
            if not match.empty: row=match.iloc[0]
        if row is not None:
            m1,m2,m3,m4=st.columns(4)
            m1.metric("National power rank", f"#{int(row['Rank'])}")
            m2.metric("Power rating", f"{float(row['Current power']):+.1f}")
            m3.metric("Preseason", f"{float(row['Preseason rating']):+.1f}")
            m4.metric("Games played", int(row["Games played"]))
            with st.expander("📈 Detailed rating breakdown", expanded=False):
                st.dataframe(pd.DataFrame([row])[['Preseason rating','On-court rating','Preseason weight','Current power','Rating change']],hide_index=True,use_container_width=True)
                st.caption("Preseason weight drops with on-court results. Missing on-court rating means the season has not supplied enough games.")
        else:
            st.info("Power ratings have not been loaded for this team. Open Model Lab to calculate them.")
        with st.expander("📈 Power rating & ranking history", expanded=False):
            saved_team_history = load_history(SPORTS[league], tid)
            if saved_team_history.empty:
                st.info("No archived daily rating snapshots for this team yet. Run 'Refresh basketball power ratings' in GitHub Actions and check again after the next successful update.")
            else:
                trend = saved_team_history.copy()
                trend["Snapshot date"] = pd.to_datetime(trend["Snapshot date"], errors="coerce")
                trend["Current power"] = pd.to_numeric(trend["Current power"], errors="coerce")
                trend["Rank"] = pd.to_numeric(trend["Rank"], errors="coerce")
                trend = trend.dropna(subset=["Snapshot date"]).sort_values("Snapshot date").drop_duplicates("Snapshot date", keep="last")
                valid_rating = trend.dropna(subset=["Current power"])
                valid_rank = trend.dropna(subset=["Rank"])
                dates_count = trend["Snapshot date"].nunique()
                if dates_count < 2:
                    st.info("One saved rating snapshot is available. Trend lines and ranking changes will appear after another dated update.")
                    if not valid_rating.empty:
                        st.metric("Saved power rating", f"{valid_rating.iloc[-1]['Current power']:+.2f}")
                    if not valid_rank.empty:
                        st.metric("Saved national rank", f"#{int(valid_rank.iloc[-1]['Rank'])}")
                else:
                    if len(valid_rating) > 1:
                        delta = valid_rating.iloc[-1]["Current power"] - valid_rating.iloc[0]["Current power"]
                        c1, c2 = st.columns(2)
                        c1.metric("Latest saved power", f"{valid_rating.iloc[-1]['Current power']:+.2f}", delta=f"{delta:+.2f} since first snapshot")
                        if len(valid_rank)>1:
                            rank_change = int(valid_rank.iloc[0]["Rank"] - valid_rank.iloc[-1]["Rank"])
                            c2.metric("National rank", f"#{int(valid_rank.iloc[-1]['Rank'])}", delta=f"{rank_change:+d} places since first snapshot")
                        st.markdown("**Power rating over time**")
                        st.line_chart(valid_rating.set_index("Snapshot date")[["Current power"]], use_container_width=True)
                    if len(valid_rank)>1:
                        st.markdown("**National rank over time** (lower is better)")
                        st.line_chart(valid_rank.set_index("Snapshot date")[["Rank"]], use_container_width=True)
                with st.expander("View dated rating records"):
                    view_cols = [c for c in ["Snapshot date", "Rank", "Current power", "Preseason rating", "On-court rating", "Games played", "Preseason weight"] if c in trend.columns]
                    st.dataframe(trend[view_cols].sort_values("Snapshot date", ascending=False), hide_index=True, use_container_width=True)
                st.caption("Only successful saved daily runs appear here. A flat graph can simply mean no games were played between snapshots; preseason numbers remain experimental.")
        team_games=games[(games["Away ID"].astype(str)==tid)|(games["Home ID"].astype(str)==tid)].copy()
        team_games["Opponent"]=team_games.apply(lambda x:x["Away"] if str(x["Home ID"])==tid else x["Home"],axis=1) if not team_games.empty else pd.Series(dtype=str)
        team_games["Location"]=team_games.apply(lambda x:"Neutral" if x["Venue"]=="Neutral" else ("Home" if str(x["Home ID"])==tid else "Away"),axis=1) if not team_games.empty else pd.Series(dtype=str)
        team_games=attach_model_lines(team_games,ratings_for_schedule,verified_d1_ids)
        st.markdown("#### Schedule and projected lines")
        st.caption(f"{len(team_games)} games found in the selected date window. Change the season coverage in the sidebar to see more.")
        if not team_games.empty:
            st.dataframe(team_games[["Date","Opponent","Location","Status","Model line","Away score","Home score"]],hide_index=True,use_container_width=True,height=390)
        else:
            st.info("No games in the loaded date range.")
        with st.expander("📊 Strength of schedule & opponents",expanded=False):
            if isinstance(sos_ratings,pd.DataFrame) and not sos_ratings.empty:
                matched=sos_ratings[sos_ratings["Team ID"].astype(str)==tid]
                if not matched.empty:
                    st.dataframe(matched[["Full SOS","Played SOS","Remaining SOS","D1 games loaded","Rating coverage %","Schedule coverage status"]],hide_index=True,use_container_width=True)
                else: st.info("No D1 SOS data for this team in the loaded window.")
            else: st.info("Calculate rankings in Model Lab, preferably with Full season selected.")
        with st.expander("📈 Strength of record",expanded=False):
            record_table = st.session_state.get(f"sor_{SPORTS[league]}")
            if isinstance(record_table,pd.DataFrame) and not record_table.empty:
                team_record = record_table[record_table["Team ID"].astype(str)==tid]
                if not team_record.empty:
                    st.dataframe(team_record[["SOR rank (provisional)","Wins","Losses","SOR games","Reference expected wins","Wins above expected","SOR score"]],hide_index=True,use_container_width=True)
                else: st.info("No completed, rated Division I results for this team yet.")
            else: st.info("Strength of record becomes available when current-season games are final and ratings have been calculated in Model Lab.")
        with st.expander("🏀 Roster analysis", expanded=False):
            @st.cache_data(ttl=86400, show_spinner=False)
            def _single_team_roster_bundle(sport, school_id, school_name):
                team_ref=pd.DataFrame([{"Team ID":str(school_id),"Team":str(school_name)}])
                snapshots, problems=audit_teams(sport, team_ref, max_teams=1)
                totals, diagnostics, errors=fetch_prior_stats(sport, team_ref, season=2026, max_games=45, max_workers=4)
                return snapshots,problems,totals,diagnostics,errors

            old_rosters, new_rosters, prior_totals, collection_status = load_saved_data(SPORTS[league])
            saved = team_saved_analysis(tid, old_rosters, new_rosters, prior_totals)
            cache_key=f"team_roster_bundle_{SPORTS[league]}_{tid}"
            bundle=st.session_state.get(cache_key)
            if bundle is not None:
                st.caption("On-demand player data (current session). Stored archive may be refreshed in the background.")
                roster_snap, roster_issues, stat_totals, stat_coverage, stat_errors=bundle
                if not roster_issues.empty: st.warning(f"{len(roster_issues)} roster requests had missing data.")
                if stat_errors: st.warning(f"{len(stat_errors)} player-stat requests were incomplete or failed.")
                if not roster_snap.empty and not stat_totals.empty:
                    returning, player_audit, notes=calculate_returning_production(roster_snap,stat_totals)
                else:
                    returning,player_audit=pd.DataFrame(),pd.DataFrame()
            elif saved is not None:
                st.caption("Using saved GitHub roster records — no manual audit needed.")
                returning=saved['returning']
                player_audit=saved['player_audit']
                stat_totals=saved['stats']
                roster_snap=pd.concat([saved['previous'],saved['current']], ignore_index=True)
                notes=saved['warnings']
            else:
                st.info("This team's data is not archived yet. It will appear automatically as the daily collection progresses.")
                returning=pd.DataFrame(); player_audit=pd.DataFrame();stat_totals=pd.DataFrame();roster_snap=pd.DataFrame();notes=[]

            if isinstance(returning,pd.DataFrame) and not returning.empty:
                r=returning.loc[returning['Team ID'].astype(str)==tid]
                if not r.empty:
                    r=r.iloc[0]
                    cols=st.columns(4)
                    for col,stat in zip(cols,['minutes','points','rebounds','assists']):
                        val=r.get(f'Returning {stat} % (known only)')
                        col.metric(f'Returning {stat}', f'{float(val):.1f}%' if pd.notna(val) else 'N/A')
                    st.caption(f"Historical roster players with documented totals: {int(r.get('Prior roster players with stats',0))} / {int(r.get('Prior roster entries',0))}. Percentages reflect documented production, not verified full-season totals.")
                with st.expander("Player matches and calculation details"):
                    if not player_audit.empty:
                        rows=player_audit[player_audit['Team ID'].astype(str)==tid] if 'Team ID' in player_audit else player_audit
                        st.dataframe(rows,hide_index=True,use_container_width=True)
                    if notes: st.caption("Some records may have incomplete coverage.")
            elif saved is not None:
                st.info("Roster snapshots are archived, but reliable returning-production percentages are not yet available.")

            st.markdown("**Incoming players and possible transfers**")
            incoming=pd.DataFrame()
            if not old_rosters.empty and not new_rosters.empty:
                incoming=build_team_roster_view(tid,old_rosters,new_rosters,prior_totals)
            if incoming.empty:
                prior_incoming=st.session_state.get(f"incoming_candidates_{SPORTS[league]}")
                if isinstance(prior_incoming,pd.DataFrame) and 'Team ID' in prior_incoming:
                    incoming=prior_incoming[prior_incoming['Team ID'].astype(str)==tid]
            if isinstance(incoming,pd.DataFrame) and not incoming.empty:
                fields=[x for x in ['Player','Prior school','Status','Previous minutes','Previous points','Previous rebounds','Previous assists'] if x in incoming]
                st.dataframe(incoming[fields],hide_index=True,use_container_width=True)
                st.caption("Prior-school matches are provisional. Unknown origin is not proof a player is a freshman; unavailable totals are not zero.")
            else:
                st.caption("No matched incoming-player data available yet. Matches improve as more schools are archived.")

            with st.expander("Experimental preseason rating — what-if analysis", expanded=False):
                st.caption("This is an assumption-driven sensitivity check, NOT a trained roster model. It never changes official rankings, projections, SOS, or SOR.")
                row = (returning[returning['Team ID'].astype(str) == tid].iloc[0]
                       if isinstance(returning, pd.DataFrame) and not returning.empty
                       and 'Team ID' in returning and (returning['Team ID'].astype(str) == tid).any()
                       else None)
                quality = roster_quality(row, incoming)
                st.warning(quality['message'])
                baseline = None
                if isinstance(team_ratings, pd.DataFrame) and not team_ratings.empty:
                    br = team_ratings[team_ratings['Team ID'].astype(str) == tid] if 'Team ID' in team_ratings else pd.DataFrame()
                    if not br.empty:
                        for field in ['Preseason rating','Current power','Power','Rating']:
                            if field in br.columns and pd.notna(br.iloc[0][field]):
                                baseline = float(br.iloc[0][field]);break
                if baseline is None:
                    st.info("First calculate power ratings in Model Lab to see the historical baseline and a hypothetical adjustment.")
                elif row is None:
                    st.info("This team needs returning-production records before a roster sensitivity can be shown.")
                else:
                    retention = pd.to_numeric(row.get('Returning minutes % (known only)'), errors='coerce')
                    if pd.isna(retention):
                        st.info("Returning minutes are unavailable; no speculative adjustment is generated.")
                    else:
                        slope = st.slider("Assumed rating points per 10 percentage points of returning minutes", 0.0, 2.0, 0.5, 0.1, key=f'roster_slope_{SPORTS[league]}_{tid}')
                        reference = st.slider("Reference retention level (%)", 20, 80, 50, 5, key=f'roster_reference_{SPORTS[league]}_{tid}')
                        scenario=roster_sensitivity(baseline, retention, reference, slope)
                        if scenario:
                            c1,c2,c3=st.columns(3)
                            c1.metric("Historical preseason baseline", f"{scenario['Historical team baseline']:+.2f}")
                            c2.metric("Hypothetical difference", f"{scenario['Hypothetical change (pts)']:+.2f}")
                            c3.metric("What-if rating", f"{scenario['Hypothetical rating (NOT validated)']:+.2f}")
                            st.caption("The default 0.5-point coefficient and 50% reference are illustrative, NOT learned from historical games. Transfer production, player quality, coaching and availability are not assigned point effects.")
                st.markdown("**Historical validation — still required**")
                st.caption("The November 2025 previous-season-only model's historical benchmark was 11.36 points MAE across 1,233 games (based on the earlier dashboard test). This is NOT a roster-model result. A fair comparison needs preseason roster snapshots dated before each tested season, previous-season player totals, and truly held-out games. No roster-model accuracy or improvement is claimed yet.")

            with st.expander("Data quality and optional refresh",expanded=False):
                st.caption("The scheduled GitHub collection is the default. Use a manual refresh only for teams not yet archived or when you need a new source check.")
                st.caption(roster_archive_summary(old_rosters,new_rosters,prior_totals,collection_status))
                if st.button("Refresh this team's roster analysis",key=f"refresh_team_roster_{SPORTS[league]}_{tid}"):
                    with st.spinner("Fetching this team's roster and historical player totals..."):
                        try:
                            st.session_state[cache_key]=_single_team_roster_bundle(SPORTS[league],tid,chosen)
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Unable to refresh: {type(exc).__name__}: {str(exc)[:180]}")
                if not stat_totals.empty:
                    st.download_button("Download documented prior-season player totals",stat_totals.to_csv(index=False).encode(),f"team_{tid}_previous_player_totals.csv","text/csv",key=f"single_roster_download_{tid}")
                st.warning("Season and roster completeness are not independently verified. These figures do not change official power ratings or game lines.")
                st.info("Experimental roster-based rating adjustments remain disabled until historical validation is completed.")
        with st.expander("👥 Roster and scouting details",expanded=False):
            if st.button("Load player roster",key="v12_roster_btn"):
                st.session_state["v12_roster_team"]=(SPORTS[league],tid)
            if st.session_state.get("v12_roster_team")== (SPORTS[league],tid):
                try:
                    athlete_df=fetch_roster(SPORTS[league],tid)
                    if athlete_df.empty: st.info("No roster data was available for this team.")
                    else: st.dataframe(athlete_df,hide_index=True,use_container_width=True)
                except Exception as exc: st.warning("Roster fetch unavailable: "+str(exc)[:160])
            st.caption("Roster listing is informational; unverified player impact is not included in ratings.")

with conference_tab:
    st.subheader("Conference rankings")
    if isinstance(conference_ratings,pd.DataFrame) and not conference_ratings.empty:
        display=conference_ratings.copy().sort_values("Average_power",ascending=False).reset_index(drop=True)
        display.insert(0,"Rank",range(1,len(display)+1))
        display=display.rename(columns={"Average_power":"Average power","Median_power":"Median power"})
        st.dataframe(display[["Rank","Conference","Teams","Average power","Top-five power"]].round(2),hide_index=True,use_container_width=True)
        with st.expander("See a conference's teams"):
            conf=st.selectbox("Conference",display["Conference"].tolist(),key="v12_conf_detail")
            if isinstance(team_ratings,pd.DataFrame):
                st.dataframe(team_ratings[team_ratings["Conference"]==conf][["Rank","Team","Current power"]],hide_index=True,use_container_width=True)
    else:
        st.info("Calculate conference power ratings in Model Lab to populate this page.")
        if not directory.empty:
            with st.expander("Browse conference memberships"):
                cf=st.selectbox("Conference",sorted(directory["Conference"].dropna().unique()),key="v12_conf_dir")
                st.dataframe(directory[directory["Conference"]==cf][["Team","Abbreviation"]],hide_index=True)

with sos_tab:
    st.subheader("Strength of schedule")
    st.caption("Provisional difficulty of D1 opponents. View full, played or remaining schedules. Coverage matters: an incomplete slate may not have a rank.")
    if isinstance(sos_ratings,pd.DataFrame) and not sos_ratings.empty:
        scope=st.segmented_control("Schedule scope",["Full SOS","Played SOS","Remaining SOS"],default="Full SOS",key="v12_sos_scope")
        scored=sos_ratings.copy().sort_values(scope,ascending=False,na_position="last")
        visible_cols=["SOS rank (provisional)","Team","Conference",scope,"D1 games loaded","Schedule coverage status"]
        st.dataframe(scored.reindex(columns=visible_cols),hide_index=True,use_container_width=True,height=480)
        with st.expander("Coverage diagnostics"):
            detail_cols=["Team","D1 games loaded","Rated games","Rating coverage %","Coverage explanation"]
            detail=scored.reindex(columns=detail_cols).copy()
            detail["Coverage explanation"]=detail["Coverage explanation"].fillna("Coverage details unavailable for this calculation. Treat SOS as provisional.")
            st.dataframe(detail,hide_index=True,use_container_width=True)
    else:
        st.info("Run the model with Full season selected to calculate schedule strength.")



with sor_tab:
    st.subheader("Strength of record")
    st.caption("How difficult has each team's achieved win-loss record been? Based on the chance a reference D1 team (rating 0) would match or exceed it against the same opponents and venues.")
    if isinstance(sor_ratings,pd.DataFrame) and not sor_ratings.empty:
        st.warning("PROVISIONAL: Results depend on loaded completed D1 games, opponent-rating quality and an uncalibrated 11-point game-margin uncertainty. A minimum of five rated final games is required to show a provisional rank. This is not an official ESPN SOR measure.")
        display=sor_ratings.copy()
        st.dataframe(display[["SOR rank (provisional)","Team","Conference","Wins","Losses","SOR games","Reference expected wins","Wins above expected","SOR score"]],hide_index=True,use_container_width=True,height=500)
        with st.expander("How this is calculated"):
            st.write("For each completed D1 game, estimate the chance a reference-strength team would beat that opponent at the same location. Calculate the exact probability the reference team would achieve at least as many wins as the real team. SOR score = −log10(that probability); higher scores indicate a more impressive record. Only completed D1-v-D1 games with rated opponents count. Missing results are excluded; rankings may be incomplete. The probabilities assume independent games and use a provisional fixed point-margin uncertainty.")
        st.download_button("Download record strength",display.to_csv(index=False).encode(),"strength_of_record.csv","text/csv")
    else:
        st.info("No completed current-season Division I games with usable results yet. SOR will populate after the season begins and you calculate ratings in Model Lab.")

st.divider()
st.caption("Data: ESPN unofficial public scoreboard feed. Historical ratings are experimental; lines are independent model estimates and not betting odds. Some game and roster data may be incomplete.")

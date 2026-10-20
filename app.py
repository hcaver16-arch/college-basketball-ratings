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



@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def calculate_power(history: pd.DataFrame):
    """Regularized least squares: margin = rating(home) - rating(away) + location.

    Estimate neutral-court team point strengths from completed games, limited to
    rows with two valid ESPN team IDs and final numeric scores. Fixed HCA is an
    explicit simplifying assumption; a later version should estimate it.
    """
    empty = pd.DataFrame(columns=["Team ID", "Team", "Power", "Games", "Win %"])
    if history.empty:
        return empty, {"games": 0, "teams": 0}
    games = history[(history["Status"] == "Final") & history["Home score"].notna() & history["Away score"].notna()].copy()
    games = games[(games["Home ID"].astype(str) != "") & (games["Away ID"].astype(str) != "") & (games["Home ID"] != games["Away ID"])]
    games = games.drop_duplicates(subset="Game ID")
    if len(games) < 20:
        return empty, {"games": int(len(games)), "teams": 0}
    tids = sorted(set(games["Home ID"]).union(games["Away ID"]))
    n = len(tids)
    index = {tid: i for i, tid in enumerate(tids)}
    mat = np.zeros((n, n), dtype=float)
    vec = np.zeros(n, dtype=float)
    played = np.zeros(n, dtype=int)
    wins = np.zeros(n, dtype=int)
    labels = {}
    # DataFrame column names contain spaces; iterrows keeps labels intact.
    for _, g in games.iterrows():
        hi, ai = index[str(g["Home ID"])], index[str(g["Away ID"])]
        # Cap blowouts to keep unusual games from dominating the fitted ratings.
        diff = float(np.clip(float(g["Home score"]) - float(g["Away score"]), -40, 40))
        margin = diff - (0.0 if g["Venue"] == "Neutral" else 3.0)
        mat[hi, hi] += 1; mat[ai, ai] += 1
        mat[hi, ai] -= 1; mat[ai, hi] -= 1
        vec[hi] += margin; vec[ai] -= margin
        played[hi] += 1; played[ai] += 1
        wins[hi] += int(diff > 0); wins[ai] += int(diff < 0)
        labels[str(g["Home ID"])] = str(g["Home"])
        labels[str(g["Away ID"])] = str(g["Away"])
    # Ridge shrinkage (prior rating zero), produces stable results even in
    # disconnected schedule components. Remove mean to keep readable scale.
    ridge = 8.0
    fit = np.linalg.solve(mat + ridge * np.eye(n), vec)
    fit -= np.mean(fit)
    result = pd.DataFrame({"Team ID": tids, "Team": [labels.get(tid, tid) for tid in tids], "Power": np.round(fit, 2), "Games": played, "Win %": np.round(100 * wins / np.maximum(played, 1), 1)})
    return result, {"games": len(games), "teams": n}



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
    effects = approved.groupby("Team ID")["Impact adjustment"].sum().clip(-12, 12).to_dict()
    ignored = len(data) - len(approved)
    return effects, data, f"{len(approved)} sourced player adjustments accepted; {ignored} ignored for missing IDs, values, or sources. Per-team adjustment capped at ±12 rating points. These manually entered point impacts are assumptions, not validated player projections."


def blending_weight(games: int):
    # Phaseout is deliberately bounded, even for a schedule with weak competition.
    anchors = [(0, 0), (5, .35), (10, .65), (15, .85), (20, .95), (25, 1.0)]
    for (g0, w0), (g1, w1) in zip(anchors, anchors[1:]):
        if games <= g1:
            return w0 + (w1 - w0) * (games - g0) / (g1 - g0)
    return 1.0


def make_combined(preseason: pd.DataFrame, current: pd.DataFrame, effects: dict):
    out = preseason[["Team ID", "Team", "Power"]].rename(columns={"Power":"Prior team rating"}).copy()
    out = out.merge(current[["Team ID", "Power", "Games"]].rename(columns={"Power": "On-court rating", "Games": "Games played"}), on="Team ID", how="left")
    out["Games played"] = out["Games played"].fillna(0).astype(int)
    out["Preseason roster adjustment"] = out["Team ID"].map(effects).fillna(0.0)
    out["Preseason rating"] = out["Prior team rating"] + out["Preseason roster adjustment"]
    out["On-court weight"] = out["Games played"].apply(blending_weight)
    out["Preseason weight"] = 1 - out["On-court weight"]
    out["Current power"] = (out["Preseason weight"] * out["Preseason rating"] +
                            out["On-court weight"] * out["On-court rating"].fillna(0.0))
    # Teams with in-season games but absent from last season get a neutral prior.
    new = current[~current["Team ID"].isin(out["Team ID"])].copy()
    if not new.empty:
        more = pd.DataFrame({"Team ID":new["Team ID"],"Team":new["Team"],"Prior team rating":0.,
            "On-court rating":new["Power"],"Games played":new["Games"].astype(int),
            "Preseason roster adjustment":new["Team ID"].map(effects).fillna(0.)})
        more["Preseason rating"] = more["Preseason roster adjustment"]
        more["On-court weight"] = more["Games played"].apply(blending_weight)
        more["Preseason weight"] = 1 - more["On-court weight"]
        more["Current power"] = more["Preseason weight"] * more["Preseason rating"] + more["On-court weight"] * more["On-court rating"]
        out = pd.concat([out, more], ignore_index=True)
    out["Rating change"] = out["Current power"] - out["Preseason rating"]
    return out.sort_values("Current power", ascending=False).reset_index(drop=True)


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
# Only display ratings calculated for this division in the current user session.
ratings_for_schedule = st.session_state.get(f"ratings_{SPORTS[league]}", {})
team_ratings = st.session_state.get(f"teams_{SPORTS[league]}")
conference_ratings = st.session_state.get(f"conferences_{SPORTS[league]}")
sos_ratings = st.session_state.get(f"sos_{SPORTS[league]}")
sor_ratings = st.session_state.get(f"sor_{SPORTS[league]}")

schedule_tab, team_tab, conference_tab, sos_tab, sor_tab, ratings_tab = st.tabs(
    ["🏀 Games", "⭐ Teams", "🏆 Conferences", "📊 Schedule strength", "📈 Record strength", "⚙️ Model Lab"])

with ratings_tab:
    st.subheader("Model Lab")
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
        sample = pd.DataFrame(columns=ROSTER_COLUMNS)
        st.download_button("Download player-input CSV template", sample.to_csv(index=False).encode(), "basketball_player_inputs.csv", "text/csv")
        uploaded_roster = st.file_uploader("Upload completed player adjustment CSV", type="csv", key="v7_roster_upload")

    roster_file = st.session_state.get("v7_roster_upload")
    ids = set(directory["Team ID"].astype(str)) if not directory.empty else set()
    effects, player_table, effect_message = roster_effects(roster_file, ids)
    st.caption(effect_message)
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
                st.write("**Season-to-date game prediction residuals (diagnostic, not a prospective backtest)**")
                errors=[]
                for _, g in current_games[current_games["Status"]=="Final"].iterrows():
                    result=game_projection(g,rating_map)
                    if result is None or pd.isna(g["Home score"]) or pd.isna(g["Away score"]):continue
                    actual=float(g["Home score"])-float(g["Away score"])
                    errors.append({"Game ID":g["Game ID"],"Predicted margin":result[0],"Actual margin":actual,"Absolute error":abs(actual-result[0])})
                if errors:
                    error_df=pd.DataFrame(errors)
                    st.metric("In-sample mean absolute margin error",f"{error_df['Absolute error'].mean():.2f} pts")
                    st.caption("These games were used to fit the ratings, so this is NOT an honest forecast accuracy estimate. A true rolling backtest must freeze predictions before tipoff. Weekly snapshots are not yet persisted by this free web application.")
                else:
                    st.info("No completed 2026–27 games with modeled teams yet. Forecast validation will begin after games have been played.")

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
        st.dataframe(scored[["SOS rank (provisional)","Team","Conference",scope,"D1 games loaded","Schedule coverage status"]],hide_index=True,use_container_width=True,height=480)
        with st.expander("Coverage diagnostics"):
            st.dataframe(scored[["Team","D1 games loaded","Rated games","Rating coverage %","Coverage explanation"]],hide_index=True,use_container_width=True)
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

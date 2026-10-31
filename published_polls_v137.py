"""V137: independent AP and Coaches college-basketball polls (display-only).

ESPN's unofficial rankings endpoint can change. Fail closed when the requested
poll is absent; never substitute Courtside power rankings for a missing poll.
"""
from __future__ import annotations
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
            rows.append({"Rank": rank, "Team": name, "Team ID": team_id,
                         "Points": entry.get("points"), "Record": entry.get("record") or ""})
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


def render_polls(league, ratings):
    st.markdown("### National polls · 2026–27")
    st.caption("AP and Coaches rankings are independent published polls, not inputs to Courtside power ratings. Data: ESPN's public rankings feed (unofficial API), cached up to six hours.")
    try:
        polls = fetch_polls(SPORTS[league])
    except Exception as exc:
        st.warning(f"Poll rankings are temporarily unavailable: {exc}")
        return
    if not polls:
        st.info("No AP or Coaches poll was returned for this division. Courtside will not display unverified or previous-season ranks as current.")
        return
    choice = st.radio("Poll", ["AP Top 25", "Coaches Poll"], horizontal=True, key="v137_poll")
    if choice not in polls:
        st.info(f"{choice} is not currently available from the poll source.")
        return
    record = polls[choice]
    frame = record["rows"].copy()
    date = record["date"]
    if date:
        st.caption(f"Published/updated: {date}")
    if isinstance(ratings, pd.DataFrame) and not ratings.empty and {"Team ID", "Current power"}.issubset(ratings.columns):
        ranks = ratings[["Team ID", "Current power"]].copy()
        ranks["Team ID"] = ranks["Team ID"].astype(str)
        ranks["Current power"] = pd.to_numeric(ranks["Current power"], errors="coerce")
        ranks["Courtside rank (all rated)"] = ranks["Current power"].rank(ascending=False, method="min")
        frame = frame.merge(ranks[["Team ID", "Courtside rank (all rated)"]].drop_duplicates("Team ID"),
                            on="Team ID", how="left")
        st.caption("Courtside rank shown for comparison only; it ranks all rated teams, including possible non-D1 opponents.")
    cols = [c for c in ["Rank", "Team", "Record", "Points", "Courtside rank (all rated)"] if c in frame]
    st.dataframe(frame[cols], hide_index=True, use_container_width=True)

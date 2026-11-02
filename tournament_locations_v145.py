"""Official 2027 NCAA tournament hosts + explicitly hypothetical regional assignments."""
from __future__ import annotations
import pandas as pd
import re
import streamlit as st
from tournament_ui_v140 import bracket_payload

MEN_REGIONS={
"East":("New York, NY","Madison Square Garden","March 26 & 28"),
"South":("San Antonio, TX","Frost Bank Center","March 25 & 27"),
"Midwest":("Kansas City, MO","T-Mobile Center","March 26 & 28"),
"West":("Los Angeles, CA","Crypto.com Arena","March 25 & 27"),
}
MEN_EARLY=[
("Pittsburgh, PA","PPG Paints Arena"),("Omaha, NE","CHI Health Center"),
("Fort Worth, TX","Dickies Arena"),("Spokane, WA","Numerica Veterans Arena"),
("Charlotte, NC","Spectrum Center"),("Minneapolis, MN","Target Center"),
("Louisville, KY","KFC Yum! Center"),("Sacramento, CA","Golden 1 Center")]
WOMEN_REGIONAL=[
("Philadelphia, PA","Xfinity Mobile Arena","March 26–29"),
("Las Vegas, NV","T-Mobile Arena","March 26–29")]
NCAA_MEN="https://www.ncaa.com/mens-final-four/future-info"
NCAA_WOMEN="https://www.ncaa.com/news/basketball-women/article/2026-05-07/2027-march-madness-womens-ncaa-tournament-schedule-dates-times"


def _region_entrants(bracket, region):
    """All potentially placed teams, including both sides of Opening Round slots."""
    opening={int(match["game"]):match for match in bracket["opening"]}
    seen=set()
    for game in region["games"]:
        for slot in (game["a"],game["b"]):
            candidates=[(slot,"Direct projected entrant")]
            if slot not in bracket["teams"]:
                match=re.match(r"^Winner OR(\d+):",slot)
                if match and int(match.group(1)) in opening:
                    pair=opening[int(match.group(1))]
                    candidates=[
                        (pair["a"],f"Opening Round {pair['game']} · contingent"),
                        (pair["b"],f"Opening Round {pair['game']} · contingent"),
                    ]
                else:
                    candidates=[]
            for name,status in candidates:
                if name in bracket["teams"] and name not in seen:
                    seen.add(name)
                    yield name,status


def projected_region_table(field, league):
    """Team-linked projected regions; no women's arena placements are invented."""
    bracket=bracket_payload(field)
    rows=[]
    for region in bracket["regions"]:
        if league=="Men's":
            city,arena,dates=MEN_REGIONS[region["name"]]
            venue=arena
            location=city
        else:
            location="Regional site not assigned"
            venue="TBD"
            dates=""
        for name,status in _region_entrants(bracket,region):
            rows.append({
                "Projected region":region["name"],
                "Team":name,
                "Overall order":bracket["teams"][name]["overall"],
                "Projected location":location,
                "Venue":venue,
                "Dates":dates,
                "Participation":status,
            })
    return pd.DataFrame(rows)


def projected_first_weekend_teams(field):
    """Men's hypothetical pod-site assignments with potential Opening Round teams."""
    from tournament_first_weekend_v151 import assign_pod_sites
    bracket=bracket_payload(field)
    assignments=assign_pod_sites(bracket)
    rows=[]
    for region in bracket["regions"]:
        for pod in range(4):
            site=assignments[(region["name"],pod)]
            # Include two R64 games per pod; expand Opening Round winner placeholders
            subset={"games":region["games"][2*pod:2*pod+2]}
            for name,status in _region_entrants(bracket,subset):
                rows.append({
                    "Projected city":site["city"] if site["city"]!="TBD" else "Site TBD",
                    "Venue":site["venue"],
                    "Projected region":region["name"],
                    "Team":name,
                    "Overall order":bracket["teams"][name]["overall"],
                    "Participation":status,
                    "Assignment basis":site["basis"],
                })
    return pd.DataFrame(rows)


def render_locations(field,league):
    st.markdown("#### Projected locations and teams")
    st.caption(
        "Teams are placed using Courtside's hypothetical bracket. "
        "Official NCAA host venues are not confirmations of any projected team assignment. "
        "Opening Round participants are potential entrants, not guaranteed regional qualifiers."
    )
    assignments=projected_region_table(field,league)
    if assignments.empty:
        st.info("No projected team-location assignments are available.")
        return
    regions=assignments["Projected region"].drop_duplicates().tolist()
    chosen=st.selectbox("Projected region",["All regions"]+regions,key="cs197_location_region")
    shown=assignments if chosen=="All regions" else assignments[assignments["Projected region"]==chosen]
    st.caption(f"{len(shown)} teams listed, including contingent Opening Round participants.")
    for region in regions:
        subset=shown[shown["Projected region"]==region].sort_values("Overall order")
        if subset.empty:
            continue
        city=str(subset.iloc[0]["Projected location"])
        venue=str(subset.iloc[0]["Venue"])
        dates=str(subset.iloc[0]["Dates"])
        with st.container(border=True):
            st.markdown(f"**{region} Region · {city}**")
            st.caption(
                (venue + (f" · {dates}" if dates else ""))
                + " · Hypothetical team assignment"
            )
            st.dataframe(
                subset[["Overall order","Team","Participation"]],
                hide_index=True,use_container_width=True
            )
    if league=="Men's":
        with st.expander("Projected first-weekend sites and teams",expanded=False):
            st.caption(
                "Four-team pods are assigned to host venues through a limited campus-geography "
                "scenario; locations may remain TBD. Pairings and site assignments are not NCAA announcements."
            )
            first=projected_first_weekend_teams(field)
            if not first.empty:
                grouped=first.groupby(["Projected city","Venue"],sort=True,dropna=False)
                for (city,venue),teams in grouped:
                    st.markdown(f"**{city} · {venue}**")
                    st.dataframe(
                        teams.sort_values("Overall order")[["Projected region","Team","Participation"]],
                        hide_index=True,use_container_width=True
                    )
        st.caption("Opening Round sites and Final Four hosts are not assigned to individual projected teams.")
    else:
        st.caption(
            "Women's regional sites are in Philadelphia and Las Vegas, but this provisional "
            "four-region bracket has no verified region-to-city mapping. Locations stay unassigned "
            "instead of guessing team sites."
        )
    source=NCAA_MEN if league=="Men's" else NCAA_WOMEN
    st.markdown(f"[Official NCAA tournament host information]({source})")

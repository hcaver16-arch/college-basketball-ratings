"""Official 2027 NCAA tournament hosts + explicitly hypothetical regional assignments."""
from __future__ import annotations
import pandas as pd
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


def projected_region_table(field, league):
    bracket=bracket_payload(field)
    if league=="Men's":
        rows=[]
        for region in bracket["regions"]:
            city,arena,dates=MEN_REGIONS[region["name"]]
            for game in region["games"]:
                for team in (game["a"],game["b"]):
                    # An Opening Round placeholder is not a known team assignment.
                    if team in bracket["teams"]:
                        rows.append({"Team":team,"Projected region":region["name"],
                            "Potential regional city":city,"Venue":arena,
                            "Official regional dates":dates,"Confidence":"Hypothetical placement"})
        return pd.DataFrame(rows)
    # Women's East/West/etc. regions are not tied to individual official
    # Philadelphia/Las Vegas sites by the current hypothetical bracket.
    return pd.DataFrame()


def render_locations(field,league):
    st.markdown("### Tournament locations · 2027")
    st.caption("Host cities and venues below are officially scheduled. Team assignments are Courtside scenarios, not NCAA announcements.")
    if league=="Men's":
        source=NCAA_MEN
        rows=[{"Region":name,"Host city":city,"Venue":venue,"Dates":dates}
              for name,(city,venue,dates) in MEN_REGIONS.items()]
        st.markdown("**Official regional venues**")
        st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
        st.markdown("**Projected team-to-region assignments**")
        st.info("These are based on Courtside's current illustrative four-region bracket. They are not independent geography-optimized projections. NCAA geography, protected seeds, rematch restrictions, and committee bracketing may change every assignment.")
        assignments=projected_region_table(field,league)
        if not assignments.empty:
            st.dataframe(assignments,hide_index=True,use_container_width=True)
        from tournament_geography_v146 import render_geographic_sites
        render_geographic_sites(field)
        st.markdown("**Official first- and second-round hosts**")
        st.dataframe(pd.DataFrame(MEN_EARLY,columns=["City","Venue"]),hide_index=True,use_container_width=True)
        st.caption("First-weekend team assignments: not projected yet. Accurate placement requires verified team-campus coordinates and NCAA bracketing constraints.")
        st.caption("Opening Round: Dayton, OH (UD Arena) and Wichita, KS (INTRUST Bank Arena). Final Four: Detroit, MI (Ford Field).")
    else:
        source=NCAA_WOMEN
        st.markdown("**Official regional hosts**")
        st.dataframe(pd.DataFrame(WOMEN_REGIONAL,columns=["City","Venue","Dates"]),hide_index=True,use_container_width=True)
        st.caption("Opening Round and first/second rounds: campus sites. Projected top-16 hosts and team placements are not available without a validated campus-location and eligibility model.")
        st.caption("Final Four: Columbus, OH · Nationwide Arena · April 2 & 4.")
    st.markdown(f"[Official NCAA tournament locations and dates]({source})")

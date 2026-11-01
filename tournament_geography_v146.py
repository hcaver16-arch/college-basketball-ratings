"""V146 geographic regional-site scenario for recognized team campuses.

The NCAA selection committee has additional protected-seed, conflict, rematch
and bracketing constraints. This is NOT an official assignment or a forecast
probability. Keep unidentified campuses as unknown rather than guessing.
"""
from __future__ import annotations
from math import asin, cos, radians, sin, sqrt
import pandas as pd
import streamlit as st

# City-center approximate coordinates, not university building locations.
CAMPUS_CITY = {
 "Texas Tech": (33.58,-101.85), "Duke":(36.00,-78.94),
 "North Carolina":(35.91,-79.05), "Kansas":(38.97,-95.24),
 "Houston":(29.76,-95.37), "Arizona":(32.22,-110.97),
 "UCLA":(34.05,-118.24), "UConn":(41.81,-72.25),
 "Gonzaga":(47.66,-117.43), "Michigan":(42.28,-83.74),
 "Michigan State":(42.74,-84.48), "Purdue":(40.43,-86.91),
 "Kentucky":(38.05,-84.50), "Tennessee":(35.96,-83.92),
 "Baylor":(31.55,-97.15), "Florida":(29.65,-82.32),
 "Auburn":(32.61,-85.48), "Alabama":(33.21,-87.57),
 "Iowa State":(42.03,-93.63), "Creighton":(41.26,-95.94),
 "Texas":(30.27,-97.74), "Wisconsin":(43.07,-89.40),
 "Illinois":(40.12,-88.24), "Indiana":(39.17,-86.53),
 "Oklahoma":(35.22,-97.44), "Arkansas":(36.06,-94.16),
 "Marquette":(43.04,-87.91), "Nebraska":(40.81,-96.70),
 "Ohio State":(40.00,-83.01), "Louisville":(38.25,-85.76),
 "St. John's":(40.73,-73.80), "BYU":(40.23,-111.66),
 "San Diego State":(32.72,-117.16), "Oregon":(44.05,-123.09),
 "Washington":(47.66,-122.31), "Cincinnati":(39.13,-84.52),
 "Villanova":(40.04,-75.34), "Virginia":(38.03,-78.48),
 "Virginia Tech":(37.23,-80.42), "Clemson":(34.68,-82.84),
 "Texas A&M":(30.63,-96.33), "TCU":(32.75,-97.33),
 "SMU":(32.84,-96.78), "Ole Miss":(34.37,-89.52),
 "Mississippi State":(33.46,-88.82), "Missouri":(38.95,-92.33),
 "Colorado":(40.02,-105.28), "Utah":(40.76,-111.89),
 "USC":(34.02,-118.29), "Stanford":(37.43,-122.17),
 "California":(37.87,-122.26),
}
REGIONAL_CITIES={
 "East": ("New York, NY", (40.75,-73.99)),
 "South": ("San Antonio, TX", (29.42,-98.49)),
 "Midwest": ("Kansas City, MO", (39.10,-94.58)),
 "West": ("Los Angeles, CA", (34.05,-118.24)),
}

def distance_miles(a,b):
    la1,lo1,la2,lo2=map(radians,(*a,*b))
    h=sin((la2-la1)/2)**2+cos(la1)*cos(la2)*sin((lo2-lo1)/2)**2
    return 3958.8*2*asin(min(1,sqrt(h)))

def campus_city(team):
    """Only exact known-school prefixes; prefer longest first to avoid collisions."""
    name=str(team).casefold()
    found=[(school,coords) for school,coords in CAMPUS_CITY.items()
           if name==school.casefold() or name.startswith(school.casefold()+" ")]
    return max(found,key=lambda item:len(item[0])) if found else (None,None)

def regional_site_scenario(field,max_protected=16):
    """Allocate recognized leading teams to regional host cities, max 4 each.

    Unverified campus geography gives Unknown; no fallback guess.
    The four-per-city cap is an illustrative seed-balance constraint.
    """
    subset=field.sort_values("Overall seed list").head(max_protected)
    remaining={key:4 for key in REGIONAL_CITIES}
    rows=[]
    for _,team in subset.iterrows():
        school,coords=campus_city(team["Team"])
        row={"Projected order":int(team["Overall seed list"]),"Team":str(team["Team"]),
             "Reference campus city":school or "Not mapped",
             "Suggested regional host":"Unknown","Approx. miles":None,
             "Basis":"No verified campus location in the local reference"}
        if coords is not None:
            choices=sorted(((distance_miles(coords,center),region)
                 for region,(_,center) in REGIONAL_CITIES.items() if remaining[region]>0))
            if choices:
                dist,region=choices[0]
                remaining[region]-=1
                row["Suggested regional host"]=REGIONAL_CITIES[region][0]
                row["Approx. miles"]=round(dist)
                row["Basis"]="Geographic proximity under four-team capacity scenario"
        rows.append(row)
    return pd.DataFrame(rows)

def render_geographic_sites(field):
    st.markdown("**Geography-informed regional site scenario · leading 16 teams**")
    st.caption("Separately estimated from the visual bracket. This does not change projected seeds or bracket slots. Campus-city coordinates are approximate and locally curated.")
    estimate=regional_site_scenario(field)
    st.dataframe(estimate,hide_index=True,use_container_width=True)
    st.caption("No probabilities: this simple proximity model omits selection committee procedures, protected seeding order, conference conflicts, rematches, pod locations and first-weekend sites. Unknown geography stays unknown. NCAA host cities are fixed; team allocations are hypothetical.")

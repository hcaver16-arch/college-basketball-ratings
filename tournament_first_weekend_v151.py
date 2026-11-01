"""Men's 2027 first-weekend pod-to-site projections.

Assign one site to each four-team bracket pod (two adjacent R64 games
and their R32 game). Each official venue receives at most two pods.
This is a geographic scenario, not the NCAA's committee assignment.
"""
from __future__ import annotations

from tournament_geography_v146 import campus_city, distance_miles

SITES = (
    ("Pittsburgh, PA", "PPG Paints Arena", (40.44, -79.99), "March 18 & 20"),
    ("Omaha, NE", "CHI Health Center", (41.26, -95.94), "March 18 & 20"),
    ("Fort Worth, TX", "Dickies Arena", (32.75, -97.36), "March 18 & 20"),
    ("Spokane, WA", "Numerica Veterans Arena", (47.66, -117.42), "March 18 & 20"),
    ("Charlotte, NC", "Spectrum Center", (35.23, -80.84), "March 19 & 21"),
    ("Minneapolis, MN", "Target Center", (44.98, -93.28), "March 19 & 21"),
    ("Louisville, KY", "KFC Yum! Center", (38.26, -85.74), "March 19 & 21"),
    ("Sacramento, CA", "Golden 1 Center", (38.58, -121.50), "March 19 & 21"),
)


def assign_pod_sites(payload):
    """Return {(region name, pod number 0..3): assignment}.

    Prefer the best-known protected seed in each four-team pod. Unknown
    campus coordinates remain TBD rather than using invented positions.
    Use an overall-seed-order greedy allocation, capacity two per host.
    """
    known=payload.get("teams", {})
    pods=[]
    for region in payload["regions"]:
        for pod in range(4):
            games=region["games"][2*pod:2*pod+2]
            entrants=[g[side] for g in games for side in ("a","b")]
            recognized=[(known[t]["overall"],t,campus_city(t)[1])
                        for t in entrants if t in known and campus_city(t)[1] is not None]
            # Only assign based on a known highest protected seed in the pod.
            lead=min(recognized,default=None)
            pods.append((lead[0] if lead else 10**6,region["name"],pod,lead))
    slots={name:2 for name,_,_,_ in SITES}
    assignments={}
    for _,region,pod,lead in sorted(pods):
        assignment={"city":"TBD","venue":"Not assigned","dates":"",
                    "basis":"Campus geography unavailable for this pod",
                    "anchor":lead[1] if lead else None,"miles":None}
        if lead:
            choices=sorted((distance_miles(lead[2],coords),name,venue,dates)
                           for name,venue,coords,dates in SITES if slots[name]>0)
            if choices:
                miles,city,venue,dates=choices[0]
                slots[city]-=1
                assignment={"city":city,"venue":venue,"dates":dates,
                    "basis":"Geographic capacity scenario, not an NCAA placement",
                    "anchor":lead[1],"miles":round(miles)}
        assignments[(region,pod)]=assignment
    return assignments


def first_weekend_label(assignments, region, round_index, game_index):
    """R64 games 0-1 map to R32 game 0, 2-3 to 1, etc."""
    pod=game_index//2 if round_index==0 else game_index
    site=assignments.get((region,pod))
    if not site or site["city"]=="TBD":
        return "First-weekend site: TBD"
    return f"Projected: {site['city']} · {site['venue']}"

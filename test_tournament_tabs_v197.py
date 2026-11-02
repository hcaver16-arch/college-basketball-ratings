"""V197 Tournament tabbed page, team-linked locations and opening-slot safety."""
from pathlib import Path
import ast
import sys
import types
import pandas as pd

for path in ("bracketology_v138.py","tournament_native_v142.py",
             "tournament_locations_v145.py","tournament_advancement_v152.py"):
    ast.parse(Path(path).read_text())
layout=Path("bracketology_v138.py").read_text()
native=Path("tournament_native_v142.py").read_text()
locations=Path("tournament_locations_v145.py").read_text()
assert '["Bracket", "Projected Field", "Advancement", "Locations"]' in layout
assert 'render_native_bracket(frame, league)' in layout
assert 'render_advancement(payload)' in layout
assert 'render_locations(frame, league)' in layout
assert 'st.columns([3.1,1.3]' in native
assert 'st.container(key="cs197_bracket_details"' in native
assert 'st.segmented_control(' in native
assert '"By region","Full bracket"' in native
assert '"courtside_requested_team_id"' in native
assert 'assign_pod_sites(bracket)' in locations
assert 'Opening Round' in locations and 'Regional site not assigned' in locations
assert 'projected_first_weekend_teams' in locations

sys.modules["streamlit"]=types.ModuleType("streamlit")
from bracketology_v138 import project_field
from tournament_ui_v140 import bracket_payload
from tournament_locations_v145 import projected_region_table, projected_first_weekend_teams

rows=[]
for c in range(32):
    for j in range(4):
        rows.append({
            "Team ID":f"{c}-{j}", "Team":f"Team {c}-{j}",
            "Conference":f"Conference {c}", "Current power":100-c-j/10,
        })
ratings=pd.DataFrame(rows)
field,error=project_field(ratings,set(ratings["Team ID"]))
assert error is None
assert len(field)==76
bracket=bracket_payload(field)

men=projected_region_table(field,"Men's")
women=projected_region_table(field,"Women's")
assert len(men)==76 and len(women)==76, (len(men),len(women))
assert men["Team"].nunique()==76 and women["Team"].nunique()==76
assert set(men["Team"])==set(field["Team"])
assert men["Projected region"].nunique()==4
assert men["Projected location"].ne("Regional site not assigned").all()
assert (women["Projected location"]=="Regional site not assigned").all()
assert (women["Venue"]=="TBD").all()
assert men["Participation"].str.contains("Opening Round").sum()==24
assert men["Participation"].eq("Direct projected entrant").sum()==52
assert set(men["Projected region"])==set(x["name"] for x in bracket["regions"])

first=projected_first_weekend_teams(field)
assert len(first)==76
assert first["Team"].nunique()==76
assert set(first["Team"])==set(field["Team"])
assert first["Participation"].str.contains("Opening Round").sum()==24
assert first["Projected region"].nunique()==4
assert not first["Projected city"].isna().any()
print("V197 tab layout, 76 linked locations, contingent teams and safe womens sites passed")

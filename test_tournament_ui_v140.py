"""Validate interactive tournament bracket inputs and conservative probability claims."""
import sys,types, math
import pandas as pd
st=types.ModuleType("streamlit")
components=types.ModuleType("streamlit.components")
v1=types.ModuleType("streamlit.components.v1")
components.v1=v1
st.components=components
sys.modules.update({"streamlit":st,"streamlit.components":components,"streamlit.components.v1":v1})
from bracketology_v138 import project_field
from tournament_ui_v140 import bracket_payload,win_probability
rows=[]
for conference in range(32):
    for i in range(4):
        rows.append({"Team ID":f"{conference}-{i}","Team":f"Team {conference}-{i}",
                     "Conference":f"Conf {conference}","Current power":100-conference-i/10})
frame=pd.DataFrame(rows)
field,error=project_field(frame,set(frame["Team ID"]))
assert not error,error
bracket=bracket_payload(field)
assert len(bracket["opening"])==12
assert len(bracket["regions"])==4
assert all(len(region["games"])==8 for region in bracket["regions"])
assert set(bracket["teams"])==set(field["Team"])
assert len(bracket["teams"])==76
assert win_probability(0,0)==0.5
assert math.isclose(win_probability(5,-5)+win_probability(-5,5),1)
assert sum(p["p"] is not None for r in bracket["regions"] for p in r["games"])>=1
print("V140 bracket structure and matchup odds passed")

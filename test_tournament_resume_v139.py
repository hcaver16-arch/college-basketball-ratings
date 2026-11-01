"""Synthetic resume blend and 76-to-64 bracket regression tests."""
import sys,types
import pandas as pd
stub=types.ModuleType("streamlit")
sys.modules["streamlit"]=stub
from bracketology_v138 import project_field
from tournament_resume_v139 import add_resume,opening_round_slots

rows=[]
for c in range(32):
    for j in range(4):
        rows.append({"Team ID":f"{c}-{j}","Team":f"Team {c}-{j}",
                     "Conference":f"Conference {c}","Current power":100-c-j/10})
r=pd.DataFrame(rows)
ids=set(r["Team ID"])
base,error=project_field(r,ids)
assert error is None and len(base)==76
assert base["SOR eligible"].sum()==0
assert base["Selection basis"].eq("Power only — SOR pending").all()
sample=pd.DataFrame([
    {"Team ID":"0-0","SOR score":3.2,"SOR games":8},
    {"Team ID":"1-0","SOR score":2.9,"SOR games":6},
    {"Team ID":"2-0","SOR score":8.0,"SOR games":2}])
projected,error=project_field(r,ids,sample)
assert error is None and len(projected)==76
assert projected["SOR eligible"].sum()==2
assert projected.loc[projected["Team ID"].eq("2-0"),"Selection basis"].iloc[0]=="Power only — SOR pending"
pairs,slots=opening_round_slots(projected)
assert len(pairs)==12 and len(slots)==64
assert slots["Team"].nunique()==64
assert projected["Opening Round (proxy)"].sum()==24
print("V139 synthetic resume and bracket tests passed")

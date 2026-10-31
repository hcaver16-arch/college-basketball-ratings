"""Synthetic 2027 76-team bracketology validation."""
import sys, types
import pandas as pd
st=types.ModuleType("streamlit")
sys.modules["streamlit"]=st
from bracketology_v138 import project_field

rows=[]
for conf in range(32):
    for i in range(4):
        id=f"{conf}-{i}"
        rows.append({"Team ID":id,"Team":id,"Conference":f"Conference {conf}","Current power":100-conf-i*.1})
data=pd.DataFrame(rows)
projected,error=project_field(data,set(data["Team ID"]))
assert error is None,error
assert len(projected)==76
assert projected["Team ID"].nunique()==76
assert projected["Bid type"].str.startswith("Projected automatic").sum()==32
assert projected["Bid type"].str.startswith("Projected at-large").sum()==44
assert projected["Opening Round (proxy)"].sum()==24
incomplete,error=project_field(data[data["Conference"]!="Conference 31"],set(data["Team ID"]))
assert incomplete.empty and error
print("V138 bracketology format and eligibility tests passed")

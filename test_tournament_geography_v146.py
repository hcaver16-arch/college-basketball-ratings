import ast
from pathlib import Path
import sys,types
import pandas as pd
sys.modules["streamlit"]=types.ModuleType("streamlit")
from tournament_geography_v146 import regional_site_scenario,campus_city,distance_miles
assert campus_city("Texas Tech Red Raiders")[0]=="Texas Tech"
assert campus_city("Unmapped Example University")== (None,None)
assert distance_miles((0,0),(0,0)) == 0
df=pd.DataFrame([{"Overall seed list":i+1,"Team":team} for i,team in enumerate(
 ["Texas Tech Red Raiders","Duke Blue Devils","Kansas Jayhawks","UCLA Bruins"]+["Unmapped Example "+str(i) for i in range(12)])])
out=regional_site_scenario(df)
assert len(out)==16
assert out.iloc[0]["Suggested regional host"]!="Unknown"
assert out["Suggested regional host"].eq("Unknown").sum()==12
assert "render_geographic_sites(field)" in Path("tournament_locations_v145.py").read_text()
for file in ("tournament_geography_v146.py","tournament_locations_v145.py"):
    ast.parse(Path(file).read_text())
print("V146 tests passed")

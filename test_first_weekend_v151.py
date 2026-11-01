"""V151 site model tests (no Streamlit runtime required)."""
from pathlib import Path
import ast, sys, types
for p in ("tournament_first_weekend_v151.py","tournament_full_v144.py","tournament_native_v142.py"):
    ast.parse(Path(p).read_text())
sys.modules["streamlit"]=types.ModuleType("streamlit")
from tournament_first_weekend_v151 import assign_pod_sites,first_weekend_label,SITES
assert len(SITES)==8
# Four regions, four pods each, four-team groups.
regions=[]
known={}
for r in ("East","West","South","Midwest"):
    games=[]
    for p in range(4):
        for k in range(2):
            a=f"{r}-A-{p}-{k}"
            b=f"{r}-B-{p}-{k}"
            games.append({"a":a,"b":b,"p":0.5})
    regions.append({"name":r,"games":games})
# Only mapped anchors deliberately assigned; others must remain TBD.
regions[0]["games"][0]["a"]="Texas Tech"
known["Texas Tech"]={"overall":1}
regions[1]["games"][0]["a"]="Duke"
known["Duke"]={"overall":2}
sites=assign_pod_sites({"teams":known,"regions":regions})
assert len(sites)==16
assert sites[("East",0)]["city"]!="TBD"
assert sites[("East",0)]["city"]==sites[("East",0)]["city"]
assert "Projected:" in first_weekend_label(sites,"East",0,0)
assert first_weekend_label(sites,"East",0,1)==first_weekend_label(sites,"East",1,0)
assert first_weekend_label(sites,"East",0,2)=="First-weekend site: TBD"
assert sum(s["city"]!="TBD" for s in sites.values())==2
from collections import Counter
assert max(Counter(s["city"] for s in sites.values() if s["city"]!="TBD").values())<=2
print("V151 pod assignments passed")

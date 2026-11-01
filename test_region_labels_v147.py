"""Seed and region labeling regression checks."""
import ast
from pathlib import Path
for name in ("tournament_region_labels_v147.py","tournament_native_v142.py","tournament_full_v144.py","bracketology_v138.py"):
    ast.parse(Path(name).read_text())
import sys,types
sys.modules["streamlit"]=types.ModuleType("streamlit")
from tournament_region_labels_v147 import seeded_label,region_site,region_seed_positions
assert sorted(region_seed_positions())==list(range(1,17))
assert seeded_label("School A",0,0,{"School A":{}})=="(1) School A"
assert seeded_label("School B",0,1,{"School B":{}})=="(16) School B"
assert seeded_label("Winner OR1",0,1,{})=="Winner OR1"
assert "Madison Square Garden" in region_site("East","Men's")[0]
assert "not yet assigned" in region_site("East","Women's")[0]
assert "render_full_overview(data, league, assignments)" in Path("tournament_native_v142.py").read_text()
print("V147 checks passed")

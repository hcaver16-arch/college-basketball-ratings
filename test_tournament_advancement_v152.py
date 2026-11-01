"""V152: synthetic 76-team bracket probability-flow regression."""
import ast
from pathlib import Path
for name in ("tournament_advancement_v152.py","tournament_native_v142.py"):
    ast.parse(Path(name).read_text())

import math
from tournament_advancement_v152 import advancement_probabilities, STAGES,win_probability
teams={}
opening=[]
for j in range(12):
    a=f"Open{j}A";b=f"Open{j}B"
    teams[a]={"power":0.0,"conference":"Test","overall":j*2+1}
    teams[b]={"power":0.0,"conference":"Test","overall":j*2+2}
    opening.append({"game":j+1,"a":a,"b":b})
slots=[f"Winner OR{j+1}: Open{j}A / Open{j}B" for j in range(12)]
for j in range(52):
    name=f"Direct{j}"
    teams[name]={"power":0.0,"conference":"Test","overall":j+25}
    slots.append(name)
regions=[]
for j,region in enumerate(("East","West","South","Midwest")):
    group=slots[j*16:(j+1)*16]
    regions.append({"name":region,"games":[{"a":group[k],"b":group[k+1]} for k in range(0,16,2)]})
p=advancement_probabilities({"teams":teams,"opening":opening,"regions":regions})
assert len(p)==76
for stage,n in zip(STAGES,(64,32,16,8,4,2,1)):
    assert math.isclose(sum(row[stage] for row in p.values()),n,abs_tol=1e-8)
assert math.isclose(win_probability(5,5),.5)
assert all(0<=prob<=1 for row in p.values() for prob in row.values())
assert math.isclose(p["Open0A"]["Win championship"],p["Open0B"]["Win championship"])
assert "render_advancement(data)" in Path("tournament_native_v142.py").read_text()
print("V152 advancement probability invariants passed")

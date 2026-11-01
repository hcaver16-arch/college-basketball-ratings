"""V145: full-season Tournament and verified regional host metadata."""
from pathlib import Path
import ast
app=Path("app.py").read_text()
assert '"Tournament"' in app.split("season_wide_pages =",1)[1].split("\n",1)[0]
for path in ("tournament_locations_v145.py","bracketology_v138.py"):
    ast.parse(Path(path).read_text())
loc=Path("tournament_locations_v145.py").read_text()
for name in ("Madison Square Garden","Frost Bank Center","T-Mobile Center","Crypto.com Arena","Xfinity Mobile Arena","T-Mobile Arena"):
    assert name in loc
assert "render_locations(frame, league)" in Path("bracketology_v138.py").read_text()
print("V145 full-season and venue metadata checks passed")

from pathlib import Path
import ast
for filename in ("tournament_region_labels_v147.py","tournament_native_v142.py","tournament_full_v144.py"):
    ast.parse(Path(filename).read_text())
native=Path("tournament_native_v142.py").read_text()
full=Path("tournament_full_v144.py").read_text()
assert "game_site_label(0, region_name, league)" in native
assert "game_site_label(idx, region_name, league)" in native
assert "game_site_label(round_index,region['name'],league)" in full
assert "First-weekend site: TBD" in Path("tournament_region_labels_v147.py").read_text()
print("V148 game location tests passed")

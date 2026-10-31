"""Ensure tournament has its own navigation destination without duplicate display."""
import ast
from pathlib import Path
source=Path("app.py").read_text()
tree=ast.parse(source)
sections=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="sections" for t in n.targets))
assert isinstance(sections,ast.List)
values=[e.value for e in sections.elts]
assert "Tournament" in values and len(values)==9
assert source.count('render_bracketology(team_ratings, verified_d1_ids, league)')==1
assert 'if selected_section == "Tournament":' in source
conference_block=source.split('if selected_section == "Conferences":',1)[1].split('if selected_section == "Tournament":',1)[0]
assert "render_bracketology" not in conference_block
print("Tournament navigation checks passed")

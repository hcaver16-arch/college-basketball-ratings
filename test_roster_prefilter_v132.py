"""V132: the team eligibility optimization keeps a single team evaluation."""
import ast
from pathlib import Path
source=Path("prospective_roster.py").read_text()
ast.parse(source)
assert "eligible = previous_ids & current_ids" in source
assert "for tid in sorted({str(x) for x in team_ids} & eligible):" in source
assert "saved = team_saved_analysis(tid, previous, current, player_totals)" in source
print("V132 roster eligibility prefilter checks passed")

"""V201: targeted selection remains opt-in and preserves the normal daily workflow."""
from pathlib import Path
import ast
source=Path("archive_roster_batch.py").read_text()
audit=Path("roster_target_audit_v201.py").read_text()
ast.parse(source)
ast.parse(audit)
assert "def run(sport,limit,repair_only=False,team_ids=None):" in source
assert "if targeted:" in source
assert "selected=schools[schools['Team ID'].astype(str).isin(targeted)].copy()" in source
assert "selected=select_batch(schools,status,limit" in source
assert "parser.add_argument('--team-ids'" in source
assert "if team_ids and args.batch < len(team_ids):" in source
assert "evidence_adjustments(prev,current,stats,set(TARGETS))" in audit
assert '"2638":"UTEP Miners"' in audit
assert '"94":"Northern Kentucky Norse"' in audit
assert 'fewer_than_8_prior_roster_players' in audit
assert 'fewer_than_90pct_prior_players_matched_to_valid_stats' in audit
print("Targeted roster refresh selectors and evidence diagnostics verified")

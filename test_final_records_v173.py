"""V173 completed games show final scores and records after result."""
import ast
from pathlib import Path
for path in ("season_records.py", "courtside_home.py", "matchup_analysis.py"):
    ast.parse(Path(path).read_text())
records=Path("season_records.py").read_text()
home=Path("courtside_home.py").read_text()
matchup=Path("matchup_analysis.py").read_text()
assert "if str(game.get('Status')) == 'Final':" in records
assert "away_score > home_score" in records
assert "home_score > away_score" in records
assert "final_score = f\"FINAL" in home
assert "Winner: {winner}" in home
assert "html.escape(final_score)" in home
assert 'record_label = "Postgame record"' in matchup
assert '· {record_label}' in matchup
print("V173 final-score and record display checks passed")

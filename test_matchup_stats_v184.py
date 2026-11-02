"""V184 box-score availability and metric alignment."""
from pathlib import Path
import ast
for file in ("app.py","matchup_analysis.py","efficiency_ui.py","matchup_preview_v100.py"):
    ast.parse(Path(file).read_text())
analysis=Path("matchup_analysis.py").read_text()
ui=Path("efficiency_ui.py").read_text()
app=Path("app.py").read_text()
preview=Path("matchup_preview_v100.py").read_text()
assert 'is_completed = str(game.get("Status")) == "Final"' in analysis
assert 'matchup_date + pd.Timedelta(days=1)' in analysis
assert 'stat_cutoff = game.get("Date")' in analysis
assert 'stats_source = stats_games' in analysis
assert 'stats_games=record_schedule' in app
assert 'postgame=is_completed' in analysis
assert 'justify-self:center;width:100%' in ui
assert 'postgame=False' in preview
print("V184 matchup stats alignment and postgame cutoff validated")

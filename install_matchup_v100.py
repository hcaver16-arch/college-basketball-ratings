"""Safely insert V100 into existing V82-style matchup analysis; idempotent."""
from pathlib import Path
import argparse,ast

IMPORT='from matchup_preview_v100 import render_matchup_preview\n'
ANCHOR='    with st.expander("Offense, defense & matchup statistics", expanded=False):\n'
OLD='        render_matchup_stats(away, home,away_stats=team_raw_stats(games,aid,league,before=game.get(\'Date\')),home_stats=team_raw_stats(games,hid,league,before=game.get(\'Date\')))\n'
NEW='''    # V100: use the same pregame raw box-score data for the concise preview and detail.\n    cs_away_stats = team_raw_stats(games,aid,league,before=game.get('Date'))\n    cs_home_stats = team_raw_stats(games,hid,league,before=game.get('Date'))\n    render_matchup_preview(away,home,away_stats=cs_away_stats,home_stats=cs_home_stats)\n    with st.expander("Offense, defense & matchup statistics", expanded=False):\n        render_matchup_stats(away,home,away_stats=cs_away_stats,home_stats=cs_home_stats)\n'''

def install(path):
    p=Path(path)
    if not p.is_file(): raise SystemExit(f'Missing: {p}')
    original=p.read_text()
    if 'render_matchup_preview(away,home,' in original:
        print('Already installed; no changes.'); return
    if original.count(ANCHOR)!=1 or original.count(OLD)!=1 or ANCHOR+OLD not in original:
        raise SystemExit('STOP: current matchup_analysis.py differs from supported V82 pattern. No changes made.')
    candidate=original.replace(ANCHOR+OLD,NEW,1)
    if IMPORT not in candidate:
        # Keep module import at top level, immediately after future annotations when possible.
        marker='from __future__ import annotations\n'
        if marker in candidate: candidate=candidate.replace(marker,marker+IMPORT,1)
        else: raise SystemExit('STOP: unexpected module layout; no changes made.')
    ast.parse(candidate,filename=str(p))
    p.write_text(candidate)
    print('Installed V100 in matchup_analysis.py')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--file',default='matchup_analysis.py')
    install(parser.parse_args().file)

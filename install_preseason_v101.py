"""Idempotent, syntax-checked insertion into V54-style team_profile_ui.py."""
from pathlib import Path
import argparse, ast
IMPORT='from preseason_profile_v101 import render_preseason_profile_v101\n'
ANCHOR="    with tabs[0]:\n"
INJECT="""    with tabs[0]:
        # V101: descriptive preseason team context, no model changes.
        render_preseason_profile_v101(team_id=team_id, division=league, rating=rating, games=games)
"""
def install(path):
    p=Path(path)
    if not p.is_file(): raise SystemExit(f'STOP: {p} was not found; no changes made.')
    original=p.read_text()
    if 'render_preseason_profile_v101(team_id=' in original:
        print('V101 already installed; no changes.');return
    if original.count(ANCHOR)!=1 or 'def render_team_profile(' not in original or 'tabs=st.tabs(' not in original:
        raise SystemExit('STOP: unsupported team_profile_ui.py layout; no changes made.')
    candidate=original.replace(ANCHOR,INJECT,1)
    future='from __future__ import annotations\n'
    if future not in candidate:raise SystemExit('STOP: expected future import missing; no changes made.')
    candidate=candidate.replace(future,future+IMPORT,1)
    ast.parse(candidate,filename=str(p))
    p.write_text(candidate)
    print('Installed V101 preseason profile in Team center → Overview.')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--file',default='team_profile_ui.py')
    install(parser.parse_args().file)

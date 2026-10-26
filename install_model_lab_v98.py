"""Fail-closed, repeatable addition to existing Streamlit Model Lab. GitHub keeps change history."""
from __future__ import annotations
import argparse
import ast
from pathlib import Path

MARKER='    # COURTSIDE_V98_PROSPECTIVE_MODEL_LAB'
INJECTION='''    # COURTSIDE_V98_PROSPECTIVE_MODEL_LAB
    from prospective_model_lab_v98 import render_prospective_model_lab
    render_prospective_model_lab()
'''

def install(path):
    original=path.read_text(encoding='utf-8')
    if MARKER in original:
        print('V98 already installed; no changes.')
        return False
    lines=original.splitlines(keepends=True)
    positions=[]
    for i,line in enumerate(lines):
        if line.strip() in ('if selected_section == "Model Lab":',"if selected_section == 'Model Lab':") and line==line.lstrip():
            positions.append(i)
    if len(positions)!=1:
        raise RuntimeError(f'Expected exactly one top-level Model Lab branch; found {len(positions)}. Refusing app.py edit.')
    pos=positions[0]
    # Insert as first code inside branch, before existing elements; no existing logic rewritten.
    lines.insert(pos+1,INJECTION)
    updated=''.join(lines)
    ast.parse(updated,filename=str(path))
    path.write_text(updated,encoding='utf-8')
    print(f'Installed V98 within Model Lab at {path}.')
    return True

def main():
    p=argparse.ArgumentParser();p.add_argument('--app',default='app.py');args=p.parse_args();install(Path(args.app))

if __name__=='__main__':main()

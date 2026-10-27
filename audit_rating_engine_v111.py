#!/usr/bin/env python3
"""Courtside V111 read-only source + rating-input audit. Stdlib only."""
import argparse, ast, csv, gzip, hashlib, json, re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DIVS=('mens-college-basketball','womens-college-basketball')
SOURCE='https://raw.githubusercontent.com/hcaver16-arch/college-basketball-ratings/main/rating_engine.py'

def read_rows(path):
    if not path.exists(): return None
    op=gzip.open if path.suffix=='.gz' else open
    with op(path,'rt',encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))

def get_literal(tree,name):
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id==name:
                    try: return ast.literal_eval(node.value)
                    except (ValueError,TypeError): return None
    return None

def function_source(tree, source, name):
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name==name:
            return ast.get_source_segment(source,node) or ''
    return ''

def scan_source(root):
    path=root/'rating_engine.py'
    if not path.is_file(): raise SystemExit('MISSING rating_engine.py at repository root')
    content=path.read_text(encoding='utf-8')
    tree=ast.parse(content)
    funcs={n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    power=function_source(tree,content,'calculate_power')
    combo=function_source(tree,content,'make_combined')
    blend=function_source(tree,content,'blending_weight')
    checks={
        'expected_three_functions_present':all(x in funcs for x in ('calculate_power','make_combined','blending_weight')),
        'fixed_home_advantage_three':bool(re.search(r'else\s+3\.0',power)),
        'blowout_capped_40':bool(re.search(r'np\.clip\([^\n]*-40\s*,\s*40',power)),
        'ridge_eight':bool(re.search(r'ridge\s*=\s*8\.0',power)),
        'minimum_twenty_finals':bool(re.search(r'len\(games\)\s*<\s*20',power)),
        'prior_zero_for_new_teams':bool(re.search(r'["\']Prior team rating["\']\s*:\s*0\.',combo)),
        'blend_saturates_by_25_games':bool(re.search(r'\(25,\s*1\.0\)',blend)),
        'team_id_type_sensitive_indexing':bool(re.search(r'index\[str\(g\[["\']Home ID["\']\]\)\]',power)),
        'uses_numeric_linear_solve': 'np.linalg.solve(' in power,
        'drops_duplicate_game_ids': 'drop_duplicates(subset="Game ID")' in power,
    }
    # These risk flags are alerts for review, not proof of a production defect.
    warnings=[]
    if checks['fixed_home_advantage_three']: warnings.append('Venue: non-neutral games always subtract 3 points; does not distinguish true home from away/unknown venue labels.')
    if checks['blowout_capped_40']: warnings.append('Margin clipping limits blowout influence but makes extreme results indistinguishable beyond 40 points.')
    if checks['ridge_eight']: warnings.append('Ridge=8 is a modeling choice; quantify shrinkage and opponent-pool coverage before tuning.')
    if checks['prior_zero_for_new_teams']: warnings.append('Absent prior-season teams receive a neutral-zero preseason prior; investigate transitional teams and cold starts.')
    if checks['team_id_type_sensitive_indexing']: warnings.append('Potential Team ID dtype mismatch: indexing str(g[ID]) while tids uses original values; verify upstream type normalization.')
    if 'Venue' in power and 'else 3.0' in power: warnings.append('Venue text may contain missing/unknown values; code treats anything other than exactly Neutral as home advantage.')
    if 'Status' in power: warnings.append('Only Final-score rows enter on-court fit; ensure incomplete or duplicated results are consistently filtered.')
    return {'file':'rating_engine.py','sha256':hashlib.sha256(content.encode()).hexdigest(),
            'lines':len(content.splitlines()),'functions':sorted(funcs),'checks':checks,'review_alerts':warnings,
            'source_url':SOURCE}

def csv_samples(root):
    out={}
    for div in DIVS:
        entry={'snapshot_found':False,'snapshot_path':None,'rows':None,'duplicate_team_ids':None,'non_numeric_power':None,'candidate_non_d1_names':[], 'fields':[]}
        paths=[root/'data'/'ratings'/div/'latest.csv.gz',root/'data'/'ratings'/div/'latest.csv']
        for p in paths:
            if not p.exists():continue
            try: rows=read_rows(p)
            except Exception as e: entry['read_error']=str(e);break
            entry['snapshot_found']=True;entry['snapshot_path']=str(p.relative_to(root));entry['rows']=len(rows)
            entry['fields']=list(rows[0].keys()) if rows else []
            key='Team ID' if 'Team ID' in entry['fields'] else 'team_id' if 'team_id' in entry['fields'] else None
            if key:
                ids=[r.get(key,'').strip() for r in rows]
                entry['duplicate_team_ids']=sum(v-1 for v in Counter(ids).values() if v>1)
                entry['blank_team_ids']=sum(not x for x in ids)
            power='Current power' if 'Current power' in entry['fields'] else 'Power' if 'Power' in entry['fields'] else None
            if power:
                invalid=0
                for r in rows:
                    try:float(r.get(power,''))
                    except (ValueError,TypeError): invalid+=1
                entry['non_numeric_power']=invalid
            break
        out[div]=entry
    return out

def repo_calls(root):
    refs=[]
    for p in root.glob('*.py'):
        if p.name=='audit_rating_engine_v111.py':continue
        try: src=p.read_text(encoding='utf-8')
        except (OSError,UnicodeError):continue
        if 'calculate_power(' in src or 'make_combined(' in src or 'blending_weight(' in src:
            refs.append({'file':p.name,'calculate_power_calls':len(re.findall(r'\bcalculate_power\(',src)),
                         'make_combined_calls':len(re.findall(r'\bmake_combined\(',src)),
                         'blending_weight_calls':len(re.findall(r'\bblending_weight\(',src))})
    return sorted(refs,key=lambda x:x['file'])

def report_md(a):
    s=a['source'];lines=['# Courtside V111 — Rating-engine integrity audit','','**READ-ONLY. No model, ratings, predictions, or site files changed.**','',f"Source SHA-256: `{s['sha256']}`",'',
    '## Observed source rules','',
    '- Model fits team strengths using regularized least squares on completed-game scoring margins.',
    '- Non-neutral games receive a fixed 3.0-point home adjustment (source-dependent).',
    '- Final margins are clipped to ±40 points.',
    '- Ridge shrinkage is set to 8.0; ratings are mean-centered after fitting.',
    '- Fewer than 20 eligible final games returns no on-court ratings.',
    '- Preseason priors blend toward on-court ratings: 0 games→0%, 5→35%, 10→65%, 15→85%, 20→95%, 25→100%.',
    '- For teams missing from previous season, code initializes preseason prior at zero.',
    '', '## Checks','', '| Check | Observed |','|---|---|']
    lines += [f'| `{k}` | {"yes" if v else "no / source differs"} |' for k,v in s['checks'].items()]
    lines += ['','## Review priorities','']
    lines += [f'- {x}' for x in s['review_alerts']]
    lines += ['','## Saved-rating snapshot health','']
    for div,r in a['snapshots'].items():
        lines.append(f"- **{div}:** {'found '+str(r.get('rows'))+' records' if r['snapshot_found'] else 'no latest file at expected path'}; duplicates={r['duplicate_team_ids']}; nonnumeric={r['non_numeric_power']}")
    lines += ['','## Relevant repository call sites','']
    lines += [f"- `{r['file']}`: calculate_power={r['calculate_power_calls']}, make_combined={r['make_combined_calls']}" for r in a['call_sites']]
    lines += ['','## Interpretation and next steps','',
    'This is **structural review**, not predictive evidence. The values above were inspected, not optimized.',
    'Next: run controlled, source-timestamp-safe experiments around HCA, ridge, priors and roster inputs; compare on the same pregame games before any live changes.',
    'Note: An off-season saved latest snapshot might reflect prior-season outcomes, not independently verified 2026–27 preseason predictions.','']
    return '\n'.join(lines)

def main():
    p=argparse.ArgumentParser();p.add_argument('--repo-root',default='.');p.add_argument('--output-dir',default='data/rating_audit_v111');args=p.parse_args()
    root=Path(args.repo_root).resolve();dest=(root/args.output_dir).resolve()
    if not dest.is_relative_to(root):raise SystemExit('Output must be inside repository')
    result={'version':111,'created_utc':datetime.now(timezone.utc).isoformat(), 'status':'READ_ONLY_STRUCTURAL_AUDIT','production_modified':False,
            'source':scan_source(root),'snapshots':csv_samples(root),'call_sites':repo_calls(root),
            'limitations':['Static checks do not establish predictive accuracy or eliminate data leakage','Source assumptions may differ from downstream line-construction code','No training or modification of official model']}
    dest.mkdir(parents=True,exist_ok=True)
    (dest/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    (dest/'report.md').write_text(report_md(result)+'\n')
    print(json.dumps({'version':111,'output':str(dest),'checks':result['source']['checks'],'snapshots':result['snapshots']},indent=2))
if __name__=='__main__': main()

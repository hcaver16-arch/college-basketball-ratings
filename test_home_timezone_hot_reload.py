"""Regression guard: Home keeps six-argument renderer even across hot reload."""
import ast
from pathlib import Path
app=ast.parse(Path("app.py").read_text())
home=ast.parse(Path("courtside_home.py").read_text())
f=next(n for n in home.body if isinstance(n,ast.FunctionDef) and n.name=="render_home")
assert len(f.args.args)==6
calls=[n for n in ast.walk(app) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="render_home"]
assert len(calls)==1 and len(calls[0].args)==6
assert 'st.session_state.get("courtside_timezone", "Central")' in Path("courtside_home.py").read_text()
print("Home renderer interface validated")

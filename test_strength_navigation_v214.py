"""V214 unified Strength page regression coverage, no model formula changes."""
import ast
from pathlib import Path

app = Path("app.py").read_text()
strength = Path("strength_pages_ui.py").read_text()
ast.parse(app)
ast.parse(strength)

# Exactly one top-level Strength navigation item, desktop and mobile.
assert 'sections=["Home","Games","Rankings","Teams","Conferences","Tournament","Strength","Model Lab"]' in app
assert 'more_pages = ["Teams", "Conferences", "Strength", "Model Lab"]' in app
assert 'season_wide_pages = {"Strength", "Conferences", "Teams", "Tournament"}' in app
assert 'if selected_section == "Strength":' in app
assert 'st.segmented_control(' in app
assert 'key="cs_strength_view"' in app
assert '["Schedule strength (SOS)", "Strength of record (SOR)"]' in app
assert 'if strength_view == "Strength of record (SOR)":' in app
assert 'render_sor(sor_ratings, league, verified_d1_ids)' in app
assert 'render_sos(sos_ratings, league, verified_d1_ids)' in app
assert 'render_sos(sos_ratings, league, verified_d1_ids)' in app.split('if selected_section == "Strength":',1)[1]
assert 'render_sor(sor_ratings, league, verified_d1_ids)' in app.split('if selected_section == "Strength":',1)[1]
assert 'if selected_section == "Schedule strength":' not in app
assert 'if selected_section == "Record strength":' not in app

# Legacy in-session navigation should retain the user's intended metric.
assert '"Schedule strength": "Schedule strength (SOS)"' in app
assert '"Record strength": "Strength of record (SOR)"' in app
assert 'if requested_page in legacy_strength_tabs:' in app
assert 'if st.session_state.get("courtside_page") in legacy_strength_tabs:' in app

# Both existing metric UIs and their independent filters, selectors, and
# navigable D1 team rows remain untouched.
for needle in (
    'def render_sos(', 'def render_sor(',
    'key=\'cs_sos_scope\'', 'key=f\'cs_{kind}_query\'',
    'key=f\'cs_{kind}_conf\'', 'key=f\'cs_{kind}_sort\'',
    'st.session_state[\'courtside_page\']=\'Teams\'',
    "'SOS rank (provisional)'", "'SOR rank (provisional)'",
    "Full SOS", "Played SOS", "Remaining SOS", "SOR score"
):
    assert needle in strength, needle
print("V214 unified SOS/SOR Strength page checks passed")

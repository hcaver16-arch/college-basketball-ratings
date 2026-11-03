"""V214/V215: one Strength nav destination, with both SOS and SOR displayed."""
import ast
from pathlib import Path

app = Path("app.py").read_text()
strength = Path("strength_pages_ui.py").read_text()
comparison = Path("strength_comparison_v215.py").read_text()
for source in (app, strength, comparison):
    ast.parse(source)

# Navigation remains combined, on mobile and desktop.
assert 'sections=["Home","Games","Rankings","Teams","Conferences","Tournament","Strength","Model Lab"]' in app
assert 'more_pages = ["Teams", "Conferences", "Strength", "Model Lab"]' in app
assert 'season_wide_pages = {"Strength", "Conferences", "Teams", "Tournament"}' in app
assert 'if selected_section == "Strength":' in app
assert 'render_strength_comparison(sos_ratings, sor_ratings, league, verified_d1_ids)' in app

# Legacy in-session navigation still lands on the combined page.
assert '"Schedule strength": "Schedule strength (SOS)"' in app
assert '"Record strength": "Strength of record (SOR)"' in app
assert 'if requested_page in legacy_strength_tabs:' in app
assert 'if st.session_state.get("courtside_page") in legacy_strength_tabs:' in app
assert 'if selected_section == "Schedule strength":' not in app
assert 'if selected_section == "Record strength":' not in app

# The two panels are rendered together rather than hidden behind a selector.
assert 'left, right = st.columns(2, gap="medium")' in comparison
assert 'with st.container(key="cs215_sos_panel", border=True):' in comparison
assert 'with st.container(key="cs215_sor_panel", border=True):' in comparison
assert 'key="cs215_shared_team_query"' in comparison
assert 'key="cs215_shared_conference"' in comparison
assert 'key=f"cs215_{kind}_sort"' in comparison
assert 'page_key = f"cs215_{kind}_page"' in comparison
assert 'st.session_state.get("courtside_logos_enabled", True)' in comparison

# Existing metric functions, formulas, and raw exports remain present.
for needle in (
    'def render_sos(', 'def render_sor(',
    "Full SOS", "Played SOS", "Remaining SOS", "SOR score",
    "'SOS rank (provisional)'", "'SOR rank (provisional)'",
):
    assert needle in strength, needle
for needle in ('SOS_FIELDS', 'SOR_FIELDS', '_navigate(team)', 'filtered[columns].to_csv', 'show_logos'):
    assert needle in comparison, needle
print("V214/V215 combined navigation and simultaneous Strength panel checks passed")

"""V215: independently sorted SOS/SOR panels share team and conference filters."""
import ast
import sys
import types
from pathlib import Path

import pandas as pd

# Data and HTML helpers do not require a running Streamlit server.
sys.modules["streamlit"] = types.ModuleType("streamlit")
from strength_pages_ui import _base
from strength_comparison_v215 import prepare_strength_rows, team_card_markup

sos = pd.DataFrame([
    {"Team ID": "10", "Team": "Alpha", "Conference": "SEC", "Full SOS": 11.0,
     "Played SOS": 10, "Remaining SOS": 12, "D1 games loaded": 29, "Rated games": 24,
     "SOS rank (provisional)": pd.NA},
    {"Team ID": "20", "Team": "Beta", "Conference": "SEC", "Full SOS": 7.0,
     "Played SOS": 5, "Remaining SOS": 9, "D1 games loaded": 31, "Rated games": 30,
     "SOS rank (provisional)": pd.NA},
    {"Team ID": "30", "Team": "C<Gamma>", "Conference": "Big Ten", "Full SOS": 9.0,
     "Played SOS": 13, "Remaining SOS": 7, "D1 games loaded": 25, "Rated games": 21,
     "SOS rank (provisional)": 5},
    {"Team ID": "40", "Team": "NonD1", "Conference": "Big Ten", "Full SOS": 40.0},
])
valid = {"10", "20", "30"}
base = _base(sos, valid)
assert len(base) == 3

def ready(**options):
    return prepare_strength_rows(base, kind="sos", score_col="Full SOS", **options)

global_order = ready(sort_col="Full SOS")
assert global_order["Team ID"].tolist() == ["10", "30", "20"]
assert global_order["_display_sos_position"].tolist() == [1.0, 2.0, 3.0]
sec = ready(sort_col="Full SOS", conference="SEC")
assert sec["Team ID"].tolist() == ["10", "20"]
# Positions do not reset inside a conference or a search result.
assert sec["_display_sos_position"].tolist() == [1.0, 3.0]
searched = ready(sort_col="Full SOS", query="beta")
assert searched["Team ID"].tolist() == ["20"]
assert searched["_display_sos_position"].tolist() == [3.0]
by_loaded = ready(sort_col="D1 games loaded")
assert by_loaded["Team ID"].tolist() == ["20", "10", "30"]
by_name = ready(sort_col="Team")
assert by_name["Team ID"].tolist() == ["10", "20", "30"]
assert ready(sort_col="Full SOS", query="nothing").empty
assert ready(sort_col="Full SOS", conference="Missing").empty

sor = pd.DataFrame([
    {"Team ID": "10", "Team": "Alpha", "Conference": "SEC",
     "SOR score": 1.4, "SOR games": 6, "Wins above expected": 3.0,
     "SOR rank (provisional)": 12},
    {"Team ID": "20", "Team": "Beta", "Conference": "SEC",
     "SOR score": 0.5, "SOR games": 2, "Wins above expected": 1.5,
     "SOR rank (provisional)": pd.NA},
    {"Team ID": "30", "Team": "C<Gamma>", "Conference": "Big Ten",
     "SOR score": 0.9, "SOR games": 7, "Wins above expected": 2.5,
     "SOR rank (provisional)": pd.NA},
])
sor_base = _base(sor, valid)
by_sor = prepare_strength_rows(sor_base, kind="sor", score_col="SOR score", sort_col="SOR score")
assert by_sor["Team ID"].tolist() == ["10", "30", "20"]
assert "_display_sos_position" not in by_sor.columns
by_games = prepare_strength_rows(sor_base, kind="sor", score_col="SOR score", sort_col="SOR games")
assert by_games["Team ID"].tolist() == ["30", "10", "20"]
sor_sec = prepare_strength_rows(sor_base, kind="sor", score_col="SOR score", sort_col="SOR score", conference="SEC")
assert len(sor_sec) == 2

html_sos = team_card_markup(global_order.iloc[0], "sos", "Full SOS", True)
assert "#1" in html_sos and "+11.0" in html_sos
assert "teamlogos/ncaa/500/10.png" in html_sos
assert "teamlogos/" not in team_card_markup(global_order.iloc[0], "sos", "Full SOS", False)
assert "Display pos." in html_sos
html_sor_ranked = team_card_markup(by_sor.iloc[0], "sor", "SOR score", False)
assert "#12" in html_sor_ranked and "1.40" in html_sor_ranked
html_sor_unranked = team_card_markup(by_sor.iloc[1], "sor", "SOR score", False)
assert "Not ranked" in html_sor_unranked and "#2" not in html_sor_unranked
html_escaped = team_card_markup(global_order.iloc[1], "sos", "Full SOS", False)
assert "&lt;Gamma&gt;" in html_escaped and "<Gamma>" not in html_escaped
assert not html_escaped.count("teamlogos/")

page = Path("strength_comparison_v215.py").read_text()
app = Path("app.py").read_text()
ast.parse(page)
ast.parse(app)
for fragment in (
    'st.columns(2, gap="medium")',
    '"cs215_sos_panel"', '"cs215_sor_panel"',
    'key="cs215_shared_team_query"', 'key="cs215_shared_conference"',
    'key="cs215_sos_scope"',
    'key=f"cs215_{kind}_sort"',
    'page_key = f"cs215_{kind}_page"',
    'page_size = 12',
    'with st.expander("Detailed data and download"',
    'st.session_state.get("courtside_logos_enabled", True)',
):
    assert fragment in page, fragment
assert "render_strength_comparison(sos_ratings, sor_ratings, league, verified_d1_ids)" in app
print("V215 side-by-side Strength data and presentation checks passed")

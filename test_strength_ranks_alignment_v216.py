"""V216: SOR display positions and aligned SOS/SOR panel controls."""
from pathlib import Path
import ast
import sys
import types
import pandas as pd

sys.modules["streamlit"] = types.ModuleType("streamlit")
from strength_comparison_v215 import prepare_strength_rows, team_card_markup, SOR_FIELDS

frame = pd.DataFrame([
    {"Team ID":"1","Team":"A","Conference":"SEC","SOR score":0.8,
     "SOR games":1,"SOR rank (provisional)":pd.NA},
    {"Team ID":"2","Team":"B","Conference":"SEC","SOR score":1.3,
     "SOR games":3,"SOR rank (provisional)":pd.NA},
    {"Team ID":"3","Team":"C","Conference":"ACC","SOR score":1.3,
     "SOR games":5,"SOR rank (provisional)":7},
    {"Team ID":"4","Team":"D","Conference":"ACC","SOR score":float("nan"),
     "SOR games":1,"SOR rank (provisional)":pd.NA},
])
sort = lambda **kwargs: prepare_strength_rows(
    frame, kind="sor", score_col="SOR score", sort_col="SOR score", **kwargs
)
all_rows = sort()
assert all_rows["Team ID"].tolist() == ["2","3","1","4"]
assert all_rows["_display_sor_position"].tolist()[:3] == [1.0,1.0,3.0]
assert pd.isna(all_rows.iloc[3]["_display_sor_position"])
assert "SOR position (display only)" in SOR_FIELDS
assert all_rows["SOR position (display only)"].tolist()[:3] == [1.0,1.0,3.0]

# Ranking doesn't reset when a shared conference filter or team search is active.
sec = sort(conference="SEC")
assert sec["Team ID"].tolist() == ["2","1"]
assert sec["_display_sor_position"].tolist() == [1.0,3.0]
team = sort(query="A")
assert len(team) == 1 and team.iloc[0]["_display_sor_position"] == 3.0

# Unqualified scores show an explicitly display-only order; eligible rankings
# retain the supplied provisional rank, including when different from score order.
assert '#1*' in team_card_markup(all_rows.iloc[0], "sor", "SOR score", False)
assert "display only" in team_card_markup(all_rows.iloc[0], "sor", "SOR score", False)
assert "#7" in team_card_markup(all_rows.iloc[1], "sor", "SOR score", False)
assert "#7*" not in team_card_markup(all_rows.iloc[1], "sor", "SOR score", False)
assert "#3*" in team_card_markup(all_rows.iloc[2], "sor", "SOR score", False)
assert "—" in team_card_markup(all_rows.iloc[3], "sor", "SOR score", False)

source=Path("strength_comparison_v215.py").read_text()
app=Path("app.py").read_text()
ast.parse(source)
ast.parse(app)
# SOS scope moved above both panels; same component sequence inside each panel:
# header, sort, count, page, rows. This prevents the screenshot's row offset.
shared = source.index('query_col, conf_col, scope_col = st.columns')
scope = source.index('"SOS scope", ["Full SOS", "Played SOS", "Remaining SOS"]')
columns = source.index('left, right = st.columns(2, gap="medium")')
sos_panel = source.index('with st.container(key="cs215_sos_panel"')
sor_panel = source.index('with st.container(key="cs215_sor_panel"')
assert shared < scope < columns < sos_panel < sor_panel
assert source.count('key="cs215_sos_scope"') == 1
assert 'min-height:73px' in source
assert 'title="{html.escape(detail)}"' in source
assert 'SOR score position (display only; not an eligible rank)' in source
assert 'st.selectbox(\n        "Sort by"' in source
assert 'page_key = f"cs215_{kind}_page"' in source
print("V216 SOR ranks, tie positions, filtering, and panel alignment passed")

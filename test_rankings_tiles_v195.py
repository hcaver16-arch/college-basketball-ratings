"""V195: ranking tiles preserve D1-only selection, navigation and the list view."""
from __future__ import annotations
import ast
from contextlib import nullcontext
from pathlib import Path
import sys
import types
import pandas as pd

source = Path("rankings_ui.py").read_text()
ast.parse(source)
for phrase in (
    '"Tiles", "Compact list"', 'key="cr195_view_mode"',
    'st.columns(3, gap="small")', 'courtside_logos_enabled',
    'cr195_tile_grid', "data['Team ID'].isin(allowed)",
    "st.session_state['courtside_page'] = 'Teams'",
    "Download filtered rankings CSV",
):
    assert phrase in source, phrase


class FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = {}
        self.markups = []
        self.htmls = []
        self.buttons = []
        self.view = "Tiles"
        self.messages = []
        self.column_calls = []
    def markdown(self, text, **kwargs): self.markups.append(text)
    def html(self, text): self.htmls.append(text)
    def info(self, text): self.messages.append(text)
    def warning(self, text): self.messages.append(text)
    def caption(self, text): pass
    def dataframe(self, *args, **kwargs): pass
    def download_button(self, *args, **kwargs): pass
    def text_input(self, *args, **kwargs): return ""
    def selectbox(self, label, options, **kwargs): return options[0]
    def segmented_control(self, *args, **kwargs): return self.view
    def number_input(self, *args, **kwargs): return 1
    def button(self, label, **kwargs):
        self.buttons.append((label, kwargs.get("key")))
        return False
    def container(self, **kwargs): return nullcontext()
    def expander(self, *args, **kwargs): return nullcontext()
    def columns(self, widths, **kwargs):
        count = widths if isinstance(widths, int) else len(widths)
        self.column_calls.append(count)
        return [nullcontext() for _ in range(count)]
    def rerun(self): raise AssertionError("No buttons were clicked")


fake = FakeStreamlit()
sys.modules["streamlit"] = fake
import rankings_ui
sample = pd.Series({
    "Rank": 3, "Team": "A & <B> College", "Team ID": "123",
    "Conference": 'Conf "West"', "Current power": 15.2,
    "Games played": 0, "Rating change": 0.0,
    "Preseason rating": 15.2,
})
html_markup = rankings_ui._tile_markup(sample, sample["Current power"], "Power rating", True)
assert "#3" in html_markup and "+15.2" in html_markup and "Games" in html_markup
assert "A &amp; &lt;B&gt; College" in html_markup and "Conf &quot;West&quot;" in html_markup
assert '<B>' not in html_markup and "Vs preseason +0.0" in html_markup
assert "teamlogos/ncaa/500/123.png" in html_markup
no_logo = rankings_ui._tile_markup(sample, 16.3, "Experimental", False)
assert "teamlogos/" not in no_logo and "cr195-monogram" in no_logo
assert "Baseline +15.2" in no_logo

data = pd.DataFrame([
    {"Team ID": "123", "Team": "A College", "Current power": 15.2, "Rank": 1,
     "Conference": "West", "Games played": 0, "Rating change": 0.0},
    {"Team ID": "456", "Team": "B College", "Current power": 13.4, "Rank": 2,
     "Conference": "East", "Games played": 1, "Rating change": 1.0},
    {"Team ID": "789", "Team": "C College", "Current power": 11.1, "Rank": 3,
     "Conference": "West", "Games played": 2, "Rating change": -0.5},
    {"Team ID": "999", "Team": "Non-D1", "Current power": 30.0, "Rank": 1,
     "Conference": "Other", "Games played": 3, "Rating change": 2.0},
])
rankings_ui.render_rankings(data, pd.DataFrame(), "Men's", {"123", "456", "789"})
tiles = [x for x in fake.htmls if "cr195-tile" in x]
assert len(tiles) == 3, len(tiles)
assert all("Non-D1" not in x for x in tiles)
assert sum(1 for label, key in fake.buttons if label == "View team →") == 3
assert 3 in fake.column_calls

fake.view = "Compact list"
fake.htmls.clear()
fake.buttons.clear()
rankings_ui.render_rankings(data, pd.DataFrame(), "Men's", {"123", "456", "789"})
assert len([x for x in fake.htmls if "cs79-grid" in x]) == 3
assert not any("cr195-tile" in x for x in fake.htmls)
assert len(fake.buttons) == 3
print("V195 rankings tiles, D1 eligibility, logo preference and list view verified")

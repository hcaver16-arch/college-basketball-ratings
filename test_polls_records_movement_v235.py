"""V235: published poll records, truthful rank movement, and saved-results fallback."""
from __future__ import annotations
import ast
from contextlib import nullcontext
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys
import types

import pandas as pd

source = Path("published_polls_v137.py").read_text()
ast.parse(source)
fake = types.ModuleType("streamlit")
fake.cache_data = lambda **kw: lambda fn: fn
fake.session_state = {"courtside_logos_enabled": True}
fake.caption = lambda *args, **kwargs: None
fake.markdown = lambda *args, **kwargs: None
fake.info = lambda *args, **kwargs: None
fake.warning = lambda msg: (_ for _ in ()).throw(AssertionError(msg))
fake.segmented_control = lambda *args, **kwargs: "Compact list"
shown = []
fake.dataframe = lambda frame, **kwargs: shown.append(frame.copy())
sys.modules["streamlit"] = fake

import published_polls_v137 as polls

payload = {"rankings": [
    {"name": "AP Top 25", "date": "2026-11-09", "ranks": [
        {"current": 5, "previous": 8, "team": {"id": "101", "displayName": "Rising U",
          "record": {"summary": "3-0"}}, "points": 1000},
        {"current": 8, "previous": 5, "team": {"id": "202", "displayName": "Falling U"},
         "recordSummary": "2-1", "points": 850},
        {"current": 9, "previous": 9, "team": {"id": "303", "displayName": "Even U"},
         "points": 750},
        {"current": 23, "previous": 0, "team": {"id": "404", "displayName": "New U"},
         "points": 99},
        {"current": 20, "team": {"id": "505", "displayName": "No Prior U"}, "points": 60},
    ]},
    {"name": "USA TODAY Coaches Poll", "date": "2026-11-09", "ranks": [
        {"current": 4, "previous": 6, "team": {"id": "101", "displayName": "Rising U",
         "record": {"summary": "3-0"}}, "points": 780},
    ]},
]}
data = polls.parse_polls(payload)
ap = data["AP Top 25"]["rows"].set_index("Team ID")
assert ap.loc["101", "Record"] == "3-0", ap.loc["101"]
assert ap.loc["202", "Record"] == "2-1"
assert ap.loc["101", "Previous poll"] == "#8"
assert ap.loc["101", "Movement"] == "▲ +3"
assert ap.loc["202", "Movement"] == "▼ -3"
assert ap.loc["303", "Movement"] == "— 0"
assert ap.loc["404", "Previous poll"] == "NR" and ap.loc["404", "Movement"] == "NEW"
assert ap.loc["505", "Movement"] == "—", "Do not guess movement without previous rank"
assert data["Coaches Poll"]["rows"].iloc[0]["Movement"] == "▲ +2"
assert polls._v235_record_text("23-3") == "23-3"
assert polls._v235_record_text({"summary": "12–1"}) == "12-1"
assert not polls._v235_record_text("1000"), "Vote points are not a W-L record"
assert not polls._v235_record_text("some record")

card = polls._poll_tile_markup(ap.loc["101"], show_logos=False)
assert "Since last poll:" in card and "▲ +3" in card and "Previously #8" in card
assert "3-0" in card and "Rising U" in card
assert "cr235-poll-change up" in card
down = polls._poll_tile_markup(ap.loc["202"], show_logos=False)
assert "▼ -3" in down and "cr235-poll-change down" in down

with TemporaryDirectory() as tmp:
    root = Path(tmp) / "data" / "ratings" / "mens-college-basketball"
    root.mkdir(parents=True)
    scores = pd.DataFrame([
        {"Game ID": "a", "Date": "2026-11-02", "Status": "Final",
         "Home ID": "303", "Away ID": "999", "Home score": 60, "Away score": 50},
        {"Game ID": "b", "Date": "2026-11-03", "Status": "Final",
         "Home ID": "303", "Away ID": "505", "Home score": 66, "Away score": 75},
        {"Game ID": "c", "Date": "2026-11-04", "Status": "Scheduled",
         "Home ID": "404", "Away ID": "999", "Home score": None, "Away score": None},
        {"Game ID": "c", "Date": "2026-11-04", "Status": "Final",
         "Home ID": "404", "Away ID": "999", "Home score": None, "Away score": None},
    ])
    scores.to_csv(root / "season_2026-27.csv.gz", compression="gzip", index=False)
    (root / "status.json").write_text(json.dumps({"snapshot_date": "2026-11-09"}))
    with patch.object(polls, "__file__", str(Path(tmp) / "published_polls_v137.py")):
        records, asof = polls._v235_saved_season_records("mens-college-basketball")
        assert records["303"] == "1-1", records
        assert records["505"] == "1-0"
        assert "404" not in records, "No score means no claimed final"
        assert asof == "2026-11-09"
        frame = data["AP Top 25"]["rows"].copy()
        filled, count, snapshot = polls._v235_fill_missing_records(frame, "mens-college-basketball")
        results = filled.set_index("Team ID")
        assert count == 2 and snapshot == "2026-11-09", (count, snapshot)
        assert results.loc["303", "Record"] == "1-1"
        assert results.loc["505", "Record"] == "1-0"
        assert results.loc["101", "Record"] == "3-0", "Never overwrite ESPN poll record"
        assert results.loc["404", "Record"] == "", "Do not invent results"
        # Missing archive is safe and still allows the rankings to render.
        assert polls._v235_saved_season_records("womens-college-basketball") == ({}, "")

with patch.object(polls, "fetch_polls", return_value=data), patch.object(
    polls, "_v235_saved_season_records", return_value=({}, "")
):
    polls.render_polls("Men's", pd.DataFrame(), poll_choice="AP Top 25")
    assert {"Movement", "Previous poll", "Record"}.issubset(shown[-1].columns)
    assert shown[-1].set_index("Team ID").loc["101", "Record"] == "3-0"
    polls.render_polls("Women's", pd.DataFrame(), poll_choice="Coaches Poll")
    assert shown[-1].iloc[0]["Movement"] == "▲ +2"

print("V235 ESPN AP/Coaches records, poll movements, fallback records, and list display passed")

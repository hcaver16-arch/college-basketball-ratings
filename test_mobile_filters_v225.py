"""V225: compact mobile filters across Courtside without changing filter semantics."""
from pathlib import Path
import ast
import sys
import types
from mobile_filters_v225 import (
    mobile_client, compact_filters_enabled, active_game_filters,
    active_filter_caption, GAME_DEFAULTS,
)

# A phone browser gets compact filters automatically; desktop does not.
assert mobile_client({"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1 Mobile/15E148"})
assert mobile_client({"user-agent": "Mozilla/5.0 (Linux; Android 16; Pixel 9) Mobile Safari/537.36"})
assert mobile_client({"user-agent": "Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X)"})
assert mobile_client({"Sec-CH-UA-Mobile": "?1"})
assert not mobile_client({"Sec-CH-UA-Mobile": "?0", "user-agent": "Safari Mobile"})
assert not mobile_client({"user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) Chrome/123 Safari/537.36"})
assert not mobile_client({"user-agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/126 Safari/537.36"})
assert not mobile_client({})
assert not mobile_client(None)
assert not mobile_client("no_headers")

# Explicit user preference overrides unreliable/missing browser hints.
fake = types.ModuleType("streamlit")
fake.session_state = {}
fake.context = types.SimpleNamespace(headers={"User-Agent": "Mozilla/5.0 (iPhone) Mobile"})
sys.modules["streamlit"] = fake
assert compact_filters_enabled()
fake.session_state["courtside_compact_filters"] = False
assert not compact_filters_enabled()
fake.session_state["courtside_compact_filters"] = True
assert compact_filters_enabled()
fake.session_state.clear()
fake.context.headers = {"User-Agent": "Mozilla/5.0 (Macintosh) Safari/605.1"}
assert not compact_filters_enabled()
del fake.context
assert not compact_filters_enabled()

# Active counts reflect actual filter selections and never reset them.
defaults = dict(GAME_DEFAULTS)
assert len(defaults) == 10
assert active_game_filters(defaults) == ()
settings = defaults | {
    "v12_game_team": "Texas Tech",
    "courtside_games_sort_v182": "Live games first",
    "games_net_q1": True,
}
assert active_game_filters(settings) == ("Sort", "Team", "Q1 only")
assert active_game_filters(defaults) == ()
assert active_filter_caption({"cr_search": "tech"}, (
    ("cr_search", "", "Search"), ("cr_sort", "Power rating", "Sort"),
)) == "Search"
assert active_filter_caption({}, (("cr_search", "", "Search"),)) == "Default filters"

names = [
    "app.py", "rankings_ui.py", "conferences_ui.py",
    "strength_comparison_v215.py", "bracketology_v138.py",
    "tournament_native_v142.py", "model_lab_center_v218.py",
    "mobile_filters_v225.py",
]
files = {p: Path(p).read_text() for p in names}
for path, body in files.items():
    ast.parse(body, filename=path)

app = files["app.py"]
assert 'settings_panel.toggle(' in app
assert '"Compact filter panels", key="courtside_compact_filters"' in app
assert 'mobile_client(st.context.headers)' in app
assert 'if compact:' in app
assert 'view = st.segmented_control(' in app
assert 'filter_panel = st.popover(' in app
assert 'filter_panel = st.container(key="cs225_games_desktop_filters")' in app
assert 'with filter_panel:' in app
assert 'active_game_filters(st.session_state)' in app
assert 'st.expander("NET quadrant filters"' in app
assert 'else st.popover("More filters"' in app
assert 'net_ranks, net_status = load_net(league)' in app
assert 'status_col, scope_col, sort_col, team_col, conf_col, venue_col, more_col' in app
assert 'with st.container(key="cs190_filter_bar"):' in app
assert 'if not compact:' in app
# Keep all original options/keys and their application to the data.
for marker in (
    "cs210_game_rank_source", "cs211_ranked_game_filter",
    "cs188_matchup_scope", "courtside_games_status_v182",
    "courtside_games_sort_v182", "v12_game_team", "v12_game_conf",
    "v12_game_venue", "games_net_quadrant", "games_net_side", "games_net_q1",
    'filter_by_ranked_teams(shown, rank_lookup, ranked_filter)',
    'if matchup_scope == "D1 vs D1 only":',
    'if view == "Live":', 'elif view == "Upcoming":', 'elif view == "Final":',
    'if team_filter != "All teams":', 'if conf_filter != "All conferences":',
    'if venue_filter != "Any location":',
    'if quadrant_filter != "All":', 'if q1_only:',
    'sort_order == "Live games first"',
    "Download filtered games CSV",
):
    assert marker in app, marker
assert 'render_matchup(' in app
assert '@st.fragment(run_every="120s")' in app

rank = files["rankings_ui.py"]
assert 'with st.popover(f"⚙ Filter rankings · {active_label}"' in rank
assert 'c1,c2,c3=st.columns([2.3,1.7,1.5])' in rank
for key in ("cr_search", "cr_conference", "cr_sort", "cr195_view_mode"):
    assert key in rank
assert "data=data[data['Conference']==conference]" in rank

conference = files["conferences_ui.py"]
assert 'with st.popover(f"⚙ Conference filters · {active_label}"' in conference
assert 'st.columns([2.4, 1.7, 1.2]' in conference
for key in ("cc_find", "cc_sort", "cs212_display"):
    assert key in conference

strength = files["strength_comparison_v215.py"]
assert 'with st.popover(f"⚙ Strength filters · {active_label}"' in strength
assert 'st.columns([2.2, 1.5, 1.3]' in strength
for key in ("cs215_shared_team_query", "cs215_shared_conference", "cs215_sos_scope"):
    assert key in strength

tournament = files["bracketology_v138.py"]
assert 'with st.popover("⚙ Projected field · Filter teams"' in tournament
assert 'key="v138_filter"' in tournament
native = files["tournament_native_v142.py"]
assert 'st.selectbox("Region", names, key="v142_region")' in native
assert 'st.radio("Region", names, horizontal=True, key="v142_region")' in native
lab = files["model_lab_center_v218.py"]
assert '"Model Lab section", SECTIONS, key="cs218_lab_section"' in lab
assert '"Model Lab sections", SECTIONS, key="cs218_lab_section"' in lab

# Pages with already compact controls (Home / Team profile) were not rewritten.
home = Path("courtside_home.py").read_text()
ast.parse(home)
assert "courtside_requested_page" in home
assert "render_home(" in home
print("V225 mobile detection, active filters, widget keys, and desktop fallback passed")

"""V198 Balanced Teams layout and real saved-history handling."""
import ast
import html
import pandas as pd
from pathlib import Path
import re

source=Path("team_profile_ui.py").read_text()
tree=ast.parse(source)
assert "tabs=st.tabs(['Overview','Schedule','Statistics','Roster','Ratings'])" in source
for section in ('with tabs[0]:','with tabs[1]:','with tabs[2]:','with tabs[3]:','with tabs[4]:'):
    assert source.count(section)==1,section
for required in (
    'cs198_rating_graph', 'cs198-snapshot', 'cs198-recent',
    'len(valid)>=2', 'st.line_chart(', "Current power",
    "render_preseason_profile_v101(", 'render_team_efficiency(raw_stats)',
    "Detailed player records", "with st.expander('Compare with another team'",
    "'courtside_selected_game_payload'", "'courtside_page']='Games'",
    "polls['AP Top 25']", "polls['Coaches Poll']",
    "history_loader(sport,str(team_id))",
):
    assert required in source,required

# Execute just pure helper functions to avoid requiring a running Streamlit server.
names={"_history_rows","_recent_results","_short_rating_row"}
funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
assert {n.name for n in funcs}==names
ns={"pd":pd,"html":html}
exec(compile(ast.Module(body=funcs,type_ignores=[]),"team_profile_ui.py","exec"),ns)
history=ns["_history_rows"]
recent=ns["_recent_results"]
assert history(None).empty
assert history(pd.DataFrame()).empty
snapshots=pd.DataFrame([
  {"Snapshot date":"2026-11-01","Current power":9.5,"Rank":12},
  {"Snapshot date":"2026-11-02","Current power":9.5,"Rank":12},
  {"Snapshot date":"2026-11-02T21:00:00Z","Current power":9.5,"Rank":11},
  {"Snapshot date":"2026-11-03","Current power":9.5,"Rank":11},
])
clean=history(snapshots)
assert len(clean)==3,clean
assert clean.iloc[1]["Rank"]==11
assert clean["Current power"].max()==clean["Current power"].min()
assert not history(pd.DataFrame([{"Snapshot date":"bad","Current power":9}])).shape[0]
one=history(snapshots.iloc[:1])
assert len(one)==1

games=pd.DataFrame([
 {"Status":"Final","Date":"2026-11-01","Opponent":"Away & <Team>",
  "Home ID":"10","Away ID":"20","Home score":85,"Away score":73},
 {"Status":"Final","Date":"2026-11-02","Opponent":"Road School",
  "Home ID":"20","Away ID":"10","Home score":71,"Away score":76},
 {"Status":"Scheduled","Date":"2026-11-03","Opponent":"Next Game",
  "Home ID":"10","Away ID":"20","Home score":None,"Away score":None},
])
results=recent(games,"10")
assert results==[("W","Road School","76–71"),("W","Away & <Team>","85–73")],results
assert recent(pd.DataFrame(),"10")==[]
assert "Away &amp; &lt;Team&gt;" in ns["_short_rating_row"]("A","Away & <Team>")
print("V198 layout, flat/deduplicated rating history and final result tests passed")

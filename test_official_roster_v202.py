"""V202: exact source-provenance joins, ambiguity rejection and player-name extraction."""
import ast
from pathlib import Path
import pandas as pd
for path in ("official_roster_reconcile_v202.py","player_stats_import.py","roster_reconciliation.py"):
    ast.parse(Path(path).read_text())
import official_roster_reconcile_v202 as mod
from player_stats_import import parse_boxscore
names=pd.DataFrame([
    {"Team ID":"1","Team":"School","Season":"2025-26","Player":"C.J. Smith",
     "Source URL":"https://school.edu/roster/2025-26","Checked UTC":"2026-11-02",
     "Source type":"Official athletics roster"},
    {"Team ID":"1","Team":"School","Season":"2025-26","Player":"Trey Horton III",
     "Source URL":"https://school.edu/roster/2025-26","Checked UTC":"2026-11-02",
     "Source type":"Official athletics roster"},
    {"Team ID":"1","Team":"School","Season":"2025-26","Player":"Unknown Player",
     "Source URL":"https://school.edu/roster/2025-26","Checked UTC":"2026-11-02",
     "Source type":"Official athletics roster"},
    {"Team ID":"1","Team":"School","Season":"2025-26","Player":"Ambiguous Name",
     "Source URL":"https://school.edu/roster/2025-26","Checked UTC":"2026-11-02",
     "Source type":"Official athletics roster"},
])
prev=pd.DataFrame([{"Team ID":"1","Player ID":"31","Player":"CJ Smith"},
                   {"Team ID":"1","Player ID":"32","Player":"Trey Horton III"}])
curr=pd.DataFrame([{"Team ID":"1","Player ID":"31","Player":"C J Smith"}])
stats=pd.DataFrame([{"Team ID":"1","Player ID":"31","Player":"CJ Smith","Minutes":88},
                    {"Team ID":"1","Player ID":"32","Player":"Trey Horton III","Minutes":55},
                    {"Team ID":"1","Player ID":"40","Player":"Ambiguous Name","Minutes":12},
                    {"Team ID":"1","Player ID":"41","Player":"Ambiguous Name","Minutes":9}])
joined=mod.reconcile(names,prev,curr,stats)
assert len(joined)==4
smith=joined[joined["Official roster player"]=="C.J. Smith"].iloc[0]
assert smith["ESPN Player ID"]=="31" and smith["Matched ESPN prior box scores"]
assert smith["Matched ESPN current roster"]
unknown=joined[joined["Official roster player"]=="Unknown Player"].iloc[0]
assert unknown["ESPN Player ID"]=="" and not unknown["Matched ESPN prior box scores"]
amb=joined[joined["Official roster player"]=="Ambiguous Name"].iloc[0]
assert amb["ESPN Player ID"]=="" and "Ambiguous" in amb["Evidence classification"]
assert mod.normalized_name("Élijàh Jones")=="elijah jones"
assert mod.normalized_name("C.J. Smith")==mod.normalized_name("CJ Smith")
counts=mod.summarize(joined,prev,curr,stats)
assert counts[0]["official_roster_players"]==4
assert counts[0]["official_names_linked_to_unique_espn_id"]==2
assert counts[0]["official_players_linked_to_prior_stats"]==2
assert counts[0]["ambiguous_matches"]==1
duplicate=pd.concat([names,names.iloc[:1]],ignore_index=True)
try:
    mod.reconcile(duplicate,prev,curr,stats)
except ValueError:
    pass
else:
    raise AssertionError("Duplicate official name not rejected")

# An ESPN boxscore is a separate game participation source with an athlete ID/name.
box={"boxscore":{"players":[{"team":{"id":"1"},"statistics":[{
   "labels":["MIN","PTS","REB","AST"],
   "athletes":[{"athlete":{"id":"31","displayName":"CJ Smith"},
                "stats":["27","18","6","4"]}]
 }]}]}}
assert parse_boxscore(box,"1","game-a")[0]["Player"]=="CJ Smith"
assert parse_boxscore(box,"1","game-a")[0]["Game ID"]=="game-a"

from roster_reconciliation import reconcile_prior_players
pool=reconcile_prior_players(
    pd.DataFrame([{"Team ID":"1","Player ID":"31","Player":"CJ Smith"}]),
    pd.DataFrame([
        {"Team ID":"1","Player ID":"31","Player":"CJ Smith","Game IDs":"g1;g2","Source":"ESPN prior boxscores"},
        {"Team ID":"1","Player ID":"33","Player":"Independent Player","Game IDs":"g2","Source":"ESPN prior boxscores"},
    ])
)
extra=pool[pool["Player ID"].eq("33")].iloc[0]
assert extra["Player"]=="Independent Player"
assert extra["In box-score totals"] and not extra["In roster snapshot"]
assert "g2" in extra["Evidence source"]
assert "not a roster snapshot" in extra["Roster source"]

reference=pd.read_csv(mod.INPUT,dtype={"Team ID":str})
new_reference=pd.read_csv(mod.CURRENT_INPUT,dtype={"Team ID":str})
assert set(reference["Team ID"])=={"2638","94"}
assert set(new_reference["Team ID"])=={"2638","94"}
assert len(reference)==28 and len(new_reference)==28
assert (reference["Season"]=="2025-26").all()
assert (new_reference["Season"]=="2026-27").all()
assert reference["Source URL"].str.startswith("https://").all()
assert new_reference["Source URL"].str.startswith("https://").all()
print("V202 official-roster matching, ambiguity protection and ESPN player provenance passed")

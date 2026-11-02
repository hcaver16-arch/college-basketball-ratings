"""V204: official-site-only parsing, exact D1 selection, evidence gates and V203 integration."""
from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import pandas as pd
import collect_official_rosters_v204 as v
import independent_roster_prospective_v203 as prospective

def page(year,names):
    return f"""<!doctype html><html><head><title>{year} Men's Basketball Roster - Official School</title></head>
    <body><nav><a class="sidearm-roster-player-name">Head Coach</a></nav>
    <h1>{year} Men's Basketball Roster</h1>
    <div id="athletes">"""+''.join(
        f'<div class="sidearm-roster-player-name"><a href="/sports/mens-basketball/roster/{str(i)}/{1000+i}">{name}</a></div>'
        for i,name in enumerate(names)
    )+"""</div><div id="staff"><p>Coaching Staff</p></div></body></html>"""

names=["Abel Stone","Ben Harper","Caleb Rivers","Daniel Foster","Ethan Carter","Frank Mitchell","Gabe Turner","Henry Morris","Isaac Brooks"]
valid,err=v.extract_roster_players(page("2025-26",names),2026)
assert not err and len(valid)==9
assert "Head Coach" not in valid
wrong,why=v.extract_roster_players(page("2026-27",names),2026)
assert not wrong and why=="roster_season_not_confirmed_by_page_heading"
tiny,why=v.extract_roster_players(page("2025-26",names[:3]),2026)
assert not tiny and "implausible" in why
assert v.safe_url("https://school.edu/sports/mens-basketball/roster/2025-26")
assert not v.safe_url("http://school.edu/sports/mens-basketball/roster")
assert not v.safe_url("https://127.0.0.1/private")
assert not v.safe_url("file:///etc/passwd")
table="""<html><title>2025-26 Men's Basketball Roster</title>
<h1>2025-26 Men's Basketball Roster</h1><table><thead><tr>
<th>No.</th><th>Full Name</th><th>Position</th></tr></thead><tbody>"""+''.join(
    f'<tr><td>{i}</td><td>{name}</td><td>G</td></tr>' for i,name in enumerate(names)
)+"""</tbody></table></html>"""
table_names,why=v.extract_roster_players(table,2026)
assert not why and table_names==names
teams=pd.DataFrame([{"Team ID":"94","Team":"Northern Kentucky Norse"},
                    {"Team ID":"2638","Team":"UTEP Miners"}])
manifest=pd.DataFrame([{"ESPN Team":n,"Prior official URL":"https://school.edu/prior",
                       "Current official URL":"https://school.edu/now"}
                     for n in ("UTEP Miners","Northern Kentucky Norse","Unknown University")])
priorities={"2638"}
selection=v.choose_targets(manifest,teams,priorities,3)
assert selection[0]["ESPN Team"]=="UTEP Miners"
assert selection[-1]["Team ID"]==""
audit,old,current=v.perform(selection,now=datetime(2026,11,2,tzinfo=timezone.utc),
    fetcher=lambda url,year:(names,None) if year==2026 else (names+["Extra Player"],None))
assert sum(r["status"]=="official_pages_parsed" for r in audit)==2
assert len(old)==18 and len(current)==20

with TemporaryDirectory() as tmp:
    root=Path(tmp)
    folder=root/v.FOLDER; folder.mkdir(parents=True)
    minimal_manifest=manifest[manifest["ESPN Team"].eq("UTEP Miners")]
    minimal_manifest.to_csv(folder/"source_manifest.csv",index=False)
    data=root/"data";data.mkdir(exist_ok=True)
    def saved(kind,frame):
        frame.to_csv(data/f"mens-college-basketball_{kind}.csv.gz",index=False,compression="gzip")
    prior=pd.DataFrame([{"Team ID":"2638","Team":"UTEP Miners","Player ID":str(i),
      "Player":names[i-1],"Roster season":2026} for i in range(1,10)])
    current_roster=pd.DataFrame([{"Team ID":"2638","Team":"UTEP Miners","Player ID":str(i),
      "Player":names[i-1],"Roster season":2027} for i in range(1,10)])
    totals=pd.DataFrame([{"Team ID":"2638","Player ID":str(i),"Player":names[i-1],
       "Minutes":100,"Source":"ESPN game verified","Game IDs":"game123","Games with box score":1}
       for i in range(1,10)])
    saved("previous_rosters",prior)
    saved("current_rosters",current_roster)
    saved("previous_stats",totals)
    orig_dir,orig_priority,orig_fetch=v.espn_directory,v.upcoming_d1_ids,v.fetch_official
    try:
        v.espn_directory=lambda sport:teams
        v.upcoming_d1_ids=lambda sport,ids,days:(priorities,[])
        v.fetch_official=lambda url,year:(names,None) if year==2026 else (names,None)
        report=v.run(root=root,limit=1,now=datetime(2026,11,2,21,tzinfo=timezone.utc))
    finally:
        v.espn_directory,v.upcoming_d1_ids,v.fetch_official=orig_dir,orig_priority,orig_fetch
    assert report["target_count"]==1 and report["source_pages_parsed"]==1
    assert report["qualified_team_count"]==1
    assert report["both_season_independently_reconciled"]==1
    assert report["qualifications"]["2638"]["prior_stats_coverage_pct"]==100
    assert report["qualifications"]["2638"]["current_identity_coverage_pct"]==100
    assert report["source_review_needed"]==0
    assert (folder/"linked_players.csv").is_file()
    snap,error=prospective.load_evidence(root,datetime(2026,11,3,tzinfo=timezone.utc))
    assert error is None,error
    assert "2638" in prospective.candidates(snap)[0]
    assert "official_roster_evidence_v204" in " ".join(snap["source_files"])

    # Stale/invalid school sites cannot generate new qualified identities.
    orig_dir,orig_priority,orig_fetch=v.espn_directory,v.upcoming_d1_ids,v.fetch_official
    try:
        v.espn_directory=lambda sport:teams
        v.upcoming_d1_ids=lambda sport,ids,days:(priorities,[])
        v.fetch_official=lambda url,year:([], "roster_season_not_confirmed_by_page_heading")
        # Preserve existing validated data only from V202, not from failed live fetches.
        fail=v.run(root=root,limit=1,now=datetime(2026,11,3,tzinfo=timezone.utc))
    finally:
        v.espn_directory,v.upcoming_d1_ids,v.fetch_official=orig_dir,orig_priority,orig_fetch
    assert fail["source_pages_parsed"]==0
    assert fail["source_review_needed"]==1
    assert fail["qualified_team_count"]==0
print("V204 official-site parsing, upcoming ranking, strict corroboration, fallback and V203 data format passed")

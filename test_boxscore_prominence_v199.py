"""V199: prominent validated box-score averages, with honest missing-value behavior."""
import ast
from pathlib import Path
import sys
import types
import html
import pandas as pd

profile=Path("team_profile_ui.py").read_text()
raw=Path("raw_team_stats.py").read_text()
eff=Path("efficiency_ui.py").read_text()
for content in (profile,raw,eff): ast.parse(content)
assert 'st.markdown(_boxscore_overview_markup(raw_stats)' in profile
assert profile.index('_boxscore_overview_markup(raw_stats)') < profile.index("st.markdown('#### Next matchup')")
assert 'st.line_chart(' in profile  # V198 history remains
assert "['Overview','Schedule','Statistics','Roster','Ratings']" in profile
assert "title == 'Box-score averages'" in eff
assert "('pts_pg', 'Points per game', 'per game')" in eff

funcs=[n for n in ast.parse(profile).body if isinstance(n,ast.FunctionDef) and n.name in ('_num','_boxscore_overview_markup')]
assert len(funcs)==2
ns={'html':html,'pd':pd}
exec(compile(ast.Module(body=funcs,type_ignores=[]),'team_profile_ui.py','exec'),ns)
render=ns['_boxscore_overview_markup']
empty=render(None)
assert empty.count("cs199-box-stat") == 6
assert empty.count('cs199-missing')==6
not_valid=render({'validated':False,'pts_pg':99})
assert "99.0" not in not_valid and not_valid.count('cs199-missing')==6
stat={'validated':True,'pts_pg':74.8,'reb_pg':36.2,'ast_pg':12.3,
      'tov_pg':9.0,'stl_pg':5.5,'blk_pg':3.1}
markup=render(stat)
for value in ('74.8','36.2','12.3','9.0','5.5','3.1'):
    assert value in markup
assert markup.count('cs199-missing')==0
partial=render({'validated':True,'pts_pg':75.0,'reb_pg':None})
assert '75.0' in partial and partial.count('cs199-missing')==5

st=types.ModuleType("streamlit")
st.cache_data=lambda **kwargs: lambda fn: fn
sys.modules['streamlit']=st
import raw_team_stats
def result(point1, point2, *, second_points=True):
    team1={'fg':(25,60),'three':(5,20),'ft':(10,15),'reb':40,'oreb':10,
           'dreb':30,'ast':18,'tov':9,'stl':5,'blk':4,'points':point1}
    team2=dict(team1)
    team2['points']=point2
    if not second_points: team2.pop('points')
    fixtures={'100000001':{'10':team1,'20':team1,'_overtime':False},
              '100000002':{'10':team2,'20':team1,'_overtime':False}}
    raw_team_stats._boxscore=lambda gid, league:fixtures[gid]
    games=pd.DataFrame([
       {'Game ID':gid,'Status':'Final','Home ID':'10','Away ID':'20',
        'Date':'2026-11-01' if i==0 else '2026-11-03'}
        for i,gid in enumerate(fixtures)
    ])
    return raw_team_stats.team_raw_stats(games,'10',"Men's")
averages=result(60,80)
assert averages['boxscore_games']==2
assert averages['pts_pg']==70
assert averages['reb_pg']==40
assert averages['ast_pg']==18
assert averages['tov_pg']==9
assert averages['stl_pg']==5
assert averages['blk_pg']==4
incomplete=result(60,80,second_points=False)
assert 'pts_pg' not in incomplete
assert incomplete['reb_pg']==40
print("V199 overview cards, PPG, missing-data gating and detailed stats verified")

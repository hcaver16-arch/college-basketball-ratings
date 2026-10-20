import math
import pandas as pd
import streamlit as st

st.set_page_config(page_title='College Basketball Ratings', page_icon='🏀', layout='wide')
st.title('🏀 College Basketball Ratings')
st.caption('Starter dashboard — upload actual team ratings and schedules. Sample figures are illustrative only.')

league = st.sidebar.radio('League', ["Men's", "Women's"])
hca = st.sidebar.slider('Home-court advantage (points)', 0.0, 6.0, 3.0, 0.5)
sigma = st.sidebar.slider('Game margin uncertainty (points)', 6.0, 20.0, 11.0, 0.5)
st.sidebar.caption('Team ratings are estimated points better/worse than average on a neutral court. Adjust when calibrating the model.')

@st.cache_data
def sample_data():
    teams = pd.DataFrame([
        ('M', 'Texas Tech', 18.5), ('M','Baylor',14.0),('M','Houston',22.0),('M','Arizona',19.0),
        ('W','South Carolina',25.0),('W','UConn',26.0),('W','Texas',22.0),('W','UCLA',24.0)
    ], columns=['league','team','rating'])
    games = pd.DataFrame([
        ('M','2026-11-10','Texas Tech','Baylor','home',None,None),
        ('M','2026-11-17','Houston','Arizona','neutral',None,None),
        ('M','2026-11-21','Baylor','Houston','home',None,None),
        ('W','2026-11-12','South Carolina','UConn','neutral',None,None),
        ('W','2026-11-18','Texas','UCLA','home',None,None),
        ('W','2026-11-22','UConn','Texas','home',None,None),
    ], columns=['league','date','home_team','away_team','venue','home_score','away_score'])
    return teams, games

demo_teams, demo_games=sample_data()
with st.sidebar.expander('Upload real data (CSV)', expanded=False):
    team_file=st.file_uploader('Team ratings CSV',type='csv',key='t')
    game_file=st.file_uploader('Game schedule/results CSV',type='csv',key='g')
    st.caption('Ratings columns: league, team, rating. Games: league, date, home_team, away_team, venue, home_score, away_score. League values M/W. Venue values home/neutral. Scores may be empty.')

try:
    teams=pd.read_csv(team_file) if team_file is not None else demo_teams
    games=pd.read_csv(game_file) if game_file is not None else demo_games
    if not {'league','team','rating'}.issubset(teams.columns):
        raise ValueError('Team ratings CSV must include league, team, rating')
    if not {'league','date','home_team','away_team','venue','home_score','away_score'}.issubset(games.columns):
        raise ValueError('Games CSV must include league, date, home_team, away_team, venue, home_score, away_score')
    lg='M' if league=="Men's" else 'W'
    t=teams.loc[teams.league==lg].copy()
    g=games.loc[games.league==lg].copy()
    t['rating']=pd.to_numeric(t['rating'],errors='raise')
    if t.team.duplicated().any():
        raise ValueError('Team names must be unique within each league')
    if t.empty:
        st.warning('No teams found for this league in your uploaded files.')
        st.stop()
    r=t.set_index('team')['rating'].to_dict()
    if not g.empty:
        for col in ['home_score','away_score']:
            g[col]=pd.to_numeric(g[col],errors='coerce')
        g['date']=pd.to_datetime(g['date'],errors='coerce')
        g['home_rating']=g.home_team.map(r)
        g['away_rating']=g.away_team.map(r)
        g['rating_gap']=g.home_rating-g.away_rating
        g['home_advantage']=g.venue.str.lower().map(lambda v: 0.0 if v=='neutral' else hca)
        g['home_margin_projection']=g.rating_gap+g.home_advantage
        g['favorite']=g.apply(lambda row: row.home_team if row.home_margin_projection>0 else (row.away_team if row.home_margin_projection<0 else 'Pick’em'),axis=1)
        g['line']=g.apply(lambda row: f"{row.favorite} -{abs(row.home_margin_projection):.1f}" if row.favorite!='Pick’em' else 'PK',axis=1)
        g['home_win_probability']=g.home_margin_projection.apply(lambda v: 100 * 0.5 * (1+math.erf(v/(sigma*math.sqrt(2)))))
        g['actual_margin']=g.home_score-g.away_score
        g['absolute_margin_error']=(g.actual_margin-g.home_margin_projection).abs()
    tabs=st.tabs(['Power rankings','Schedules & lines','Strength of schedule','Model accuracy'])
    with tabs[0]:
        st.subheader(f'{league} power rankings')
        st.dataframe(t.sort_values('rating',ascending=False).reset_index(drop=True).assign(rank=lambda x:x.index+1)[['rank','team','rating']],hide_index=True,use_container_width=True)
    with tabs[1]:
        st.subheader('Schedule and model lines')
        if g.empty:
            st.info('No games uploaded for this league.')
        else:
            team_filter=st.selectbox('Show games for', ['All teams']+sorted(t.team.tolist()))
            visible=g if team_filter=='All teams' else g[(g.home_team==team_filter)|(g.away_team==team_filter)]
            display=visible[['date','away_team','home_team','venue','line','home_win_probability','away_score','home_score']].copy()
            display['date']=display['date'].dt.strftime('%Y-%m-%d')
            st.dataframe(display.rename(columns={'away_team':'Away','home_team':'Home','venue':'Venue','line':'Model line','home_win_probability':'Home win %','away_score':'Away score','home_score':'Home score','date':'Date'}),hide_index=True,use_container_width=True,column_config={'Home win %':st.column_config.NumberColumn(format='%.1f%%')})
            st.caption('These lines use rating difference + home-court adjustment. They are not sportsbook odds. Projected totals/scores require a pace and offensive/defensive efficiency model.')
    with tabs[2]:
        st.subheader('Strength of schedule')
        st.caption('Initial metric: mean opponent neutral-court rating. Later: opponent-adjusted location-aware expected wins.')
        records=[]
        for team in t.team:
            opponents=[]
            if not g.empty:
                opponents += [r.get(x) for x in g.loc[g.home_team==team,'away_team']]
                opponents += [r.get(x) for x in g.loc[g.away_team==team,'home_team']]
            opponents=[x for x in opponents if x is not None]
            records.append({'Team':team,'Scheduled games':len(opponents),'Average opponent rating':sum(opponents)/len(opponents) if opponents else float('nan')})
        sos=pd.DataFrame(records).sort_values('Average opponent rating',ascending=False,na_position='last').reset_index(drop=True)
        sos.insert(0,'SOS rank',sos.index+1)
        st.dataframe(sos,hide_index=True,use_container_width=True)
    with tabs[3]:
        st.subheader('Model prediction errors')
        if g.empty or g.actual_margin.notna().sum()==0:
            st.info('No completed games with final scores yet.')
        else:
            played=g[g.actual_margin.notna()]
            st.metric('Games with scores',len(played))
            st.metric('Mean absolute spread error',f"{played.absolute_margin_error.mean():.1f} pts")
            st.dataframe(played[['date','away_team','home_team','home_margin_projection','actual_margin','absolute_margin_error']],hide_index=True,use_container_width=True)
    if team_file is None or game_file is None:
        st.info('DEMO MODE: At least one input still uses invented sample data. Do not interpret displayed teams, dates, lines or ratings as real 2026–27 information.')
except Exception as e:
    st.error(f'Unable to load the data: {e}')

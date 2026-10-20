"""November holdout comparisons. No future games are used to compute preseason ratings."""
import math
import numpy as np
import pandas as pd

COLUMNS=['Team ID','Impact adjustment','Source','Known by date']
CUTOFF=pd.Timestamp('2025-11-01')

def historical_adjustments(uploaded, valid_ids):
    if uploaded is None:
        return {}, pd.DataFrame(), 'No archived roster-impact file provided. Only the prior-season baseline can be tested.'
    try:
        df=pd.read_csv(uploaded,dtype={'Team ID':str})
    except Exception as e:
        return {},pd.DataFrame(),f'Cannot read CSV: {e}'
    missing=set(COLUMNS)-set(df.columns)
    if missing:
        return {},df,'Missing required columns: '+', '.join(sorted(missing))
    df=df.copy()
    df['Team ID']=df['Team ID'].astype(str).str.strip()
    df['Impact adjustment']=pd.to_numeric(df['Impact adjustment'],errors='coerce')
    df['Known by date parsed']=pd.to_datetime(df['Known by date'],errors='coerce')
    source=df['Source'].fillna('').astype(str).str.strip()
    valid=(df['Team ID'].isin(set(map(str,valid_ids))) & df['Impact adjustment'].notna() & (source!='') & df['Known by date parsed'].notna() & (df['Known by date parsed']<=CUTOFF))
    df['Accepted']=valid
    if not valid.any():
        return {},df,'No dated, sourced historical player adjustments passed validation. The roster comparison is disabled.'
    adj=df[valid].groupby('Team ID')['Impact adjustment'].sum().clip(-12,12).to_dict()
    return adj,df,f'{int(valid.sum())} sourced, date-eligible rows accepted; {int((~valid).sum())} excluded. These adjustments are user estimates, not independently validated player impact.'

def compare_early_season(previous_games,test_games,allowed_ids=None,roster_changes=None,start='2025-11-01',end='2025-12-01',home_advantage=3.0,margin_sd=11.0):
    # import here to share identical fit method with existing historical validation
    from model_testing import fit_ratings
    def eligible(df):
        wanted=['Date','Status','Home ID','Away ID','Home score','Away score','Venue','Game ID']
        if not set(wanted).issubset(df.columns):
            return pd.DataFrame(), 'Missing columns: '+', '.join(sorted(set(wanted)-set(df.columns)))
        x=df.copy()
        x=x[(x['Status']=='Final') & x['Home score'].notna() & x['Away score'].notna()]
        x['Home ID']=x['Home ID'].astype(str); x['Away ID']=x['Away ID'].astype(str)
        x=x[(x['Home ID']!='') & (x['Away ID']!='') & (x['Home ID']!=x['Away ID'])]
        if allowed_ids is not None:
            s=set(map(str,allowed_ids));x=x[x['Home ID'].isin(s) & x['Away ID'].isin(s)]
        x['parsed date']=pd.to_datetime(x['Date'],errors='coerce')
        x=x.dropna(subset=['parsed date']).drop_duplicates('Game ID')
        return x, None
    prior, err=eligible(previous_games)
    if err:return pd.DataFrame(),{},err
    test,err=eligible(test_games)
    if err:return pd.DataFrame(),{},err
    # Lock training to before 2025-07-01. Test is exclusively Nov 2025.
    prior=prior[prior['parsed date']<pd.Timestamp('2025-07-01')]
    test=test[(test['parsed date']>=pd.Timestamp(start)) & (test['parsed date']<pd.Timestamp(end))]
    if prior.empty or test.empty:return pd.DataFrame(),{},'Historical baseline or November holdout is empty.'
    r=fit_ratings(prior)
    changes=roster_changes or {}
    rows=[]
    for _,g in test.iterrows():
        h,a=str(g['Home ID']),str(g['Away ID'])
        if h not in r or a not in r:continue
        hca=0.0 if g['Venue']=='Neutral' else home_advantage
        base=r[h]-r[a]+hca
        adjusted=base+changes.get(h,0.)-changes.get(a,0.)
        actual=float(g['Home score'])-float(g['Away score'])
        if actual==0:continue
        row={'Date':str(g['Date']),'Game ID':str(g['Game ID']),'Home':str(g.get('Home',h)),'Away':str(g.get('Away',a)), 'Actual margin':actual,'Previous-season margin':base,'Home-only margin':hca, 'Home won':int(actual>0)}
        if changes:row['Roster-adjusted margin']=adjusted
        rows.append(row)
    x=pd.DataFrame(rows)
    if x.empty:return x,{},'No November games where both teams had previous-season ratings.'
    metrics=[]
    for name,col in [('Previous-season','Previous-season margin'),('Home-only','Home-only margin'),('Roster-adjusted','Roster-adjusted margin')]:
        if col not in x:continue
        pred=x[col].to_numpy(float);act=x['Actual margin'].to_numpy(float)
        p=np.array([0.5*(1+math.erf(float(v)/(margin_sd*math.sqrt(2)))) for v in pred])
        metrics.append({'Model':name,'Games':len(x),'Margin MAE':float(np.mean(np.abs(pred-act))),'Winner accuracy':float(np.mean((pred>0)==(act>0))),'Brier score':float(np.mean((p-x['Home won'].to_numpy(float))**2))})
    return x,pd.DataFrame(metrics),None

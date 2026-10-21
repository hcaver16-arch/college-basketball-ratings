"""Experimental universal roster-adjusted basketball power ratings.

The slope, prior center and reliability scaling are scenario assumptions, NOT trained coefficients.
Missing data yields a zero adjustment, never a zero team rating. Independent from official ratings.
"""
from __future__ import annotations
import pandas as pd
from prospective_roster import evidence_adjustments

MODEL_VERSION = 'preliminary-v41'

def build_preliminary_ratings(ratings, previous, current, totals, slope=0.5):
    required={'Team ID','Current power'}
    if ratings is None or ratings.empty or not required.issubset(ratings.columns):
        return pd.DataFrame()
    df=ratings.copy()
    df['Team ID']=df['Team ID'].astype(str)
    # Reuse the exact existing validated descriptive-data threshold as v36/v40.
    info=evidence_adjustments(previous,current,totals,set(df['Team ID']),slope=slope)
    n_games=pd.to_numeric(df.get('Games played',pd.Series(0,index=df.index)),errors='coerce').fillna(0).clip(lower=0)
    prior_weight=pd.to_numeric(df.get('Preseason weight',pd.Series(1.0,index=df.index)),errors='coerce').fillna(1.0).clip(0,1)
    df['Roster return minutes %']=df['Team ID'].map(lambda k:info.get(k,{}).get('retention'))
    df['Roster source match count']=df['Team ID'].map(lambda k:info.get(k,{}).get('matched',0))
    # evidence_adjustments only returns teams satisfying >=8 previous roster entries and >=90% ID/stat matching.
    df['Roster data status']=df['Team ID'].map(lambda k:'Qualified descriptive data' if k in info else 'No qualifying evidence — baseline fallback')
    df['Raw roster scenario change']=df['Team ID'].map(lambda k:info.get(k,{}).get('adjustment',0.0)).astype(float)
    # Actual-game performance overtakes preseason assumptions using the existing model's preseason weight.
    df['Roster adjustment']= (df['Raw roster scenario change']*prior_weight).round(3)
    df['Experimental power']=pd.to_numeric(df['Current power'],errors='coerce')+df['Roster adjustment']
    valid=df['Experimental power'].notna()
    df['Experimental rank']=pd.NA
    df.loc[valid,'Experimental rank']=df.loc[valid,'Experimental power'].rank(ascending=False,method='min').astype(int)
    df['Roster evidence applied']=df['Team ID'].isin(info)
    df['Model version']=MODEL_VERSION
    return df

def add_experimental_lines(games, experimental, d1_ids, home_advantage=3.0):
    shown=games.copy()
    shown['Experimental line']='Not rated'
    shown['Roster input status']='Unavailable'
    if experimental is None or experimental.empty:return shown
    lookup=experimental.drop_duplicates('Team ID').set_index('Team ID')
    d1={str(t) for t in d1_ids}
    for idx,g in shown.iterrows():
        h,a=str(g.get('Home ID','')),str(g.get('Away ID',''))
        if h not in d1 or a not in d1:continue
        if h not in lookup.index or a not in lookup.index:continue
        hp,ap=lookup.at[h,'Experimental power'],lookup.at[a,'Experimental power']
        if pd.isna(hp) or pd.isna(ap):continue
        adv=0 if str(g.get('Venue','')).lower()=='neutral' else home_advantage
        margin=float(hp)-float(ap)+adv
        favored=g.get('Home') if margin>=0 else g.get('Away')
        shown.at[idx,'Experimental line']=f'{favored} -{abs(margin):.1f}'
        applied=int(bool(lookup.at[h,'Roster evidence applied']))+int(bool(lookup.at[a,'Roster evidence applied']))
        shown.at[idx,'Roster input status']=('Both teams' if applied==2 else 'One team' if applied==1 else 'Baseline fallback')
    return shown

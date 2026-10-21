"""Read-only pairing of locked baseline and later independent roster forecasts."""
import pandas as pd


def combined_forecasts(baseline, roster, classifications=None):
    if baseline is None or baseline.empty:
        return pd.DataFrame()
    out=baseline.copy()
    out['Game ID']=out['Game ID'].astype(str)
    if out['Game ID'].duplicated().any():
        raise ValueError('Duplicate locked baseline Game IDs')
    # The embedded roster prediction in the FIRST baseline record is distinct
    # from the later independent roster prediction; do not present it as later.
    out=out.rename(columns={'Roster experimental home margin':'Roster margin at first forecast',
                            'Roster eligible':'Roster eligible at first forecast'})
    if roster is not None and not roster.empty:
        r=roster.copy()
        r['Game ID']=r['Game ID'].astype(str)
        r['Roster forecast UTC']=pd.to_datetime(r['Roster forecast UTC'],utc=True,errors='coerce')
        r['Game start UTC']=pd.to_datetime(r['Game start UTC'],utc=True,errors='coerce')
        r=r[r['Roster forecast UTC'].notna() & r['Game start UTC'].notna() &
            (r['Roster forecast UTC'] < r['Game start UTC'])]
        if r['Game ID'].duplicated().any():
            raise ValueError('Duplicate separate roster Game IDs')
        keep=['Game ID','Roster forecast UTC','Roster experimental home margin',
              'Home retention %','Away retention %','Baseline home margin at roster forecast',
              'Roster model version']
        r=r[[c for c in keep if c in r.columns]].rename(columns={
            'Roster experimental home margin':'Later roster home margin',
            'Home retention %':'Later home retention %',
            'Away retention %':'Later away retention %'})
        out=out.merge(r,on='Game ID',how='left',validate='one_to_one')
    else:
        out['Later roster home margin']=float('nan')
        out['Roster forecast UTC']=pd.NaT
    if classifications is not None and not classifications.empty and 'Matchup class' in classifications:
        c=classifications[['Game ID','Matchup class']].copy()
        c['Game ID']=c['Game ID'].astype(str)
        out=out.merge(c.drop_duplicates('Game ID',keep='last'),on='Game ID',how='left',validate='one_to_one')
    out['Later roster available']=out['Later roster home margin'].notna()
    return out


def roster_diagnostics(locked, existing_roster, adjustments, now):
    """Count unlocked *roster* opportunities independently of new baseline eligibility."""
    existing=set(existing_roster['Game ID'].astype(str)) if existing_roster is not None and not existing_roster.empty else set()
    totals={'locked_games_checked':0,'already_has_roster_forecast':0,
            'past_tipoff':0,'invalid_tipoff':0,'missing_home_roster':0,
            'missing_away_roster':0,'missing_both_rosters':0,'missing_baseline_margin':0,
            'ready_for_new_roster_forecast':0}
    if locked is None or locked.empty:return totals
    ts=pd.Timestamp(now)
    if ts.tzinfo is None:ts=ts.tz_localize('UTC')
    for row in locked.to_dict('records'):
        totals['locked_games_checked']+=1
        if str(row['Game ID']) in existing:
            totals['already_has_roster_forecast']+=1;continue
        start=pd.to_datetime(row.get('Game start UTC'),utc=True,errors='coerce')
        if pd.isna(start):totals['invalid_tipoff']+=1;continue
        if ts>=start:totals['past_tipoff']+=1;continue
        h=str(row['Home ID']) in adjustments
        a=str(row['Away ID']) in adjustments
        if not h and not a:totals['missing_both_rosters']+=1;continue
        if not h:totals['missing_home_roster']+=1;continue
        if not a:totals['missing_away_roster']+=1;continue
        if pd.isna(pd.to_numeric(row.get('Baseline home margin'),errors='coerce')):
            totals['missing_baseline_margin']+=1;continue
        totals['ready_for_new_roster_forecast']+=1
    return totals

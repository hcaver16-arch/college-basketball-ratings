"""Independent, pre-tip roster forecast records and D1 classification.

Does not alter the first-forecast archive or backfill a roster prediction after tipoff.
"""
import pandas as pd

EXTRA_FIELDS=['Division','Game ID','Roster forecast UTC','Game start UTC','Home ID','Away ID',
              'Roster experimental home margin','Home retention %','Away retention %',
              'Baseline home margin at roster forecast','Roster model version']


def matchup_classifications(schedule, d1_ids):
    items=[]
    for g in schedule.to_dict('records'):
        home=str(g['Home ID']) in d1_ids
        away=str(g['Away ID']) in d1_ids
        items.append({'Game ID':str(g['Game ID']),'Home D1':home,'Away D1':away,
                      'Matchup class':'D1 vs D1' if home and away else ('D1 vs non-D1' if home or away else 'Non-D1 vs non-D1')})
    return pd.DataFrame(items,columns=['Game ID','Home D1','Away D1','Matchup class'])


def new_roster_forecasts(archive, existing, adjustments, now):
    saved=set(existing['Game ID'].astype(str)) if not existing.empty else set()
    rows=[]
    for g in archive.to_dict('records'):
        gid=str(g['Game ID'])
        start=pd.to_datetime(g['Game start UTC'],utc=True,errors='coerce')
        if gid in saved or pd.isna(start) or not pd.Timestamp(now)<start:continue
        h,a=str(g['Home ID']),str(g['Away ID'])
        if h not in adjustments or a not in adjustments:continue
        baseline=pd.to_numeric(g['Baseline home margin'],errors='coerce')
        if pd.isna(baseline):continue
        margin=float(baseline)+adjustments[h]['adjustment']-adjustments[a]['adjustment']
        rows.append({'Division':g['Division'],'Game ID':gid,'Roster forecast UTC':pd.Timestamp(now).isoformat(),
                     'Game start UTC':start.isoformat(),'Home ID':h,'Away ID':a,
                     'Roster experimental home margin':round(margin,2),
                     'Home retention %':adjustments[h]['retention'],'Away retention %':adjustments[a]['retention'],
                     'Baseline home margin at roster forecast':float(baseline),
                     'Roster model version':'retention-v1-untrained'})
    return pd.DataFrame(rows,columns=EXTRA_FIELDS)


def join_evaluation(baseline_eval,roster_archive,classifications):
    if baseline_eval.empty:return baseline_eval
    out=baseline_eval.copy()
    if not classifications.empty:
        out=out.merge(classifications[['Game ID','Matchup class']].drop_duplicates('Game ID'),on='Game ID',how='left')
    # The separate roster forecast has its own pre-tip UTC timestamp. Missing means not eligible.
    out=out.drop(columns=['Roster absolute error'],errors='ignore')
    if roster_archive.empty:
        out['Roster absolute error']=float('nan')
        return out
    r=roster_archive[['Game ID','Roster forecast UTC','Game start UTC','Roster experimental home margin']].copy()
    r['Game ID']=r['Game ID'].astype(str)
    r['Roster forecast UTC']=pd.to_datetime(r['Roster forecast UTC'],utc=True,errors='coerce')
    r['Game start UTC']=pd.to_datetime(r['Game start UTC'],utc=True,errors='coerce')
    r=r[r['Roster forecast UTC']<r['Game start UTC']].drop_duplicates('Game ID')
    r=r.rename(columns={'Roster experimental home margin':'Later roster margin'}).drop(columns=['Game start UTC'])
    out=out.merge(r[['Game ID','Later roster margin','Roster forecast UTC']],on='Game ID',how='left')
    out['Roster absolute error']=(out['Actual home margin']-pd.to_numeric(out['Later roster margin'],errors='coerce')).abs()
    return out

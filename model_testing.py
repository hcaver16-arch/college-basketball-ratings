"""Walk-forward, out-of-sample game-margin backtesting utilities.

The routine never fits on the week it predicts. No roster-history claims are made.
"""
import math
import numpy as np
import pandas as pd


def fit_ratings(games, ridge=8.0, home_advantage=3.0):
    if games.empty:
        return {}
    ids = sorted(set(games['Home ID'].astype(str)) | set(games['Away ID'].astype(str)))
    index = {tid: j for j, tid in enumerate(ids)}
    n = len(ids)
    if n < 2:
        return {}
    a = np.eye(n) * ridge
    b = np.zeros(n)
    for _, g in games.iterrows():
        h, aw = index[str(g['Home ID'])], index[str(g['Away ID'])]
        if h == aw:
            continue
        observed = float(np.clip(g['Home score'] - g['Away score'], -40, 40))
        adjusted = observed - (0.0 if g['Venue'] == 'Neutral' else home_advantage)
        a[h,h] += 1; a[aw,aw] += 1; a[h,aw] -= 1; a[aw,h] -= 1
        b[h] += adjusted; b[aw] -= adjusted
    x = np.linalg.solve(a, b)
    x -= np.mean(x)
    return dict(zip(ids, x))


def walk_forward_backtest(history, allowed_ids=None, min_training_days=45, step_days=14, margin_sd=11.0):
    required = {'Date','Status','Home ID','Away ID','Home score','Away score','Venue','Game ID'}
    if not required.issubset(history.columns):
        raise ValueError('Missing game columns: ' + ', '.join(sorted(required - set(history.columns))))
    df = history.copy()
    df = df[(df['Status'] == 'Final') & df['Home score'].notna() & df['Away score'].notna()].copy()
    df['Home ID'] = df['Home ID'].astype(str)
    df['Away ID'] = df['Away ID'].astype(str)
    df = df[(df['Home ID'] != '') & (df['Away ID'] != '') & (df['Home ID'] != df['Away ID'])]
    if allowed_ids is not None:
        allowed = set(map(str,allowed_ids))
        df = df[df['Home ID'].isin(allowed) & df['Away ID'].isin(allowed)]
    df = df.drop_duplicates('Game ID')
    df['Game date'] = pd.to_datetime(df['Date'], errors='coerce').dt.normalize()
    df = df[df['Game date'].notna()].sort_values(['Game date','Game ID'])
    if df.empty:
        return pd.DataFrame(), {'reason': 'No eligible completed games'}
    cut = df['Game date'].min() + pd.Timedelta(days=min_training_days)
    final = df['Game date'].max()
    records = []
    folds = 0
    while cut <= final:
        train = df[df['Game date'] < cut]
        test = df[(df['Game date'] >= cut) & (df['Game date'] < cut + pd.Timedelta(days=step_days))]
        if len(train) >= 50 and not test.empty:
            ratings = fit_ratings(train)
            folds += 1
            for _, g in test.iterrows():
                home, away = str(g['Home ID']), str(g['Away ID'])
                if home not in ratings or away not in ratings:
                    continue
                hca = 0.0 if g['Venue'] == 'Neutral' else 3.0
                predicted = float(ratings[home] - ratings[away] + hca)
                actual = float(g['Home score']) - float(g['Away score'])
                if actual == 0:
                    continue
                prob = 0.5 * (1 + math.erf(predicted / (margin_sd * math.sqrt(2))))
                records.append({'Date':str(g['Date']),'Game ID':str(g['Game ID']),
                                'Home':str(g.get('Home', home)), 'Away':str(g.get('Away', away)),
                                'Model margin':round(predicted,3),'Actual margin':actual,'Home win probability':prob,
                                'Baseline margin':hca,'Predicted winner correct':int((predicted > 0) == (actual > 0)),
                                'Home won':int(actual > 0)})
        cut += pd.Timedelta(days=step_days)
    result = pd.DataFrame(records)
    if result.empty:
        return result, {'reason':'No games with both teams previously rated','folds':folds,'final_games':len(df)}
    errors = result['Model margin'] - result['Actual margin']
    base = result['Baseline margin'] - result['Actual margin']
    stats = {'games_tested':len(result),'folds':folds,'MAE':float(errors.abs().mean()),'RMSE':float(np.sqrt((errors**2).mean())),
             'Baseline MAE':float(base.abs().mean()),'Win accuracy':float(result['Predicted winner correct'].mean()),
             'Brier score':float(((result['Home win probability']-result['Home won'])**2).mean()),
             'date_first':result['Date'].min(),'date_last':result['Date'].max(),'final_games':len(df)}
    return result,stats

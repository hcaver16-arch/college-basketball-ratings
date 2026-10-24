"""Independent experimental opponent-adjusted efficiency model.

Not part of Courtside's official power ratings or pregame prediction archive.
Fit a regularized, additive two-way model of points per 100 estimated possessions.
Both offenses and defenses are estimated jointly, with the average defense
constrained to zero, and a small fixed home-court term estimated from data.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

REQUIRED = {"game_id", "date", "home_id", "away_id", "home_points", "away_points", "possessions"}


def fit_adjusted_efficiency(games: pd.DataFrame, *, prior_games: float = 8.0, min_games: int = 3,
                            min_league_games: int = 30) -> pd.DataFrame:
    """Fit a snapshot using only games already finished as of the snapshot date.

    Output is deliberately sparse: teams with too few completed paired box scores
    have NaN ratings. Game sample and season coverage must accompany all values.
    """
    columns = ["Team ID", "adj_o", "adj_d", "adj_em", "games_used", "league_games", "method"]
    if games is None or not isinstance(games, pd.DataFrame) or not REQUIRED.issubset(games.columns):
        return pd.DataFrame(columns=columns)
    frame = games.copy().drop_duplicates("game_id")
    for col in ["home_points", "away_points", "possessions"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["home_id", "away_id", "home_points", "away_points", "possessions"])
    frame = frame[(frame.possessions >= 35) & (frame.possessions <= 120) &
                  (frame.home_points >= 0) & (frame.away_points >= 0) &
                  (frame.home_id.astype(str) != frame.away_id.astype(str))]
    frame = frame.reset_index(drop=True)
    if len(frame) < min_league_games:
        return pd.DataFrame(columns=columns)
    ids = sorted(set(frame.home_id.astype(str)) | set(frame.away_id.astype(str)))
    index = {tid: i for i, tid in enumerate(ids)}
    n = len(ids)
    # Each game produces two equations, home offense vs away defense and inverse.
    # y = intercept + offense[team] - defense[opponent] + home_edge.
    # The ridge prior shrinks poor/small-sample estimates to the league mean.
    x = np.zeros((2 * len(frame), 2 * n + 2), dtype=float)
    y = np.zeros(2 * len(frame), dtype=float)
    counts = np.zeros(n, dtype=int)
    for i, rec in enumerate(frame.itertuples(index=False)):
        h, a = index[str(rec.home_id)], index[str(rec.away_id)]
        counts[h] += 1; counts[a] += 1
        j = i * 2
        x[j, 0] = 1; x[j, 1 + h] = 1; x[j, 1 + n + a] = -1; x[j, -1] = 1
        x[j+1, 0] = 1; x[j+1, 1 + a] = 1; x[j+1, 1 + n + h] = -1
        y[j] = 100 * float(rec.home_points) / float(rec.possessions)
        y[j+1] = 100 * float(rec.away_points) / float(rec.possessions)
    penalty = np.full(x.shape[1], float(prior_games))
    penalty[0] = 0.0  # league mean intercept is unpenalized
    penalty[-1] = 24.0  # home edge shrinks substantially as well
    lhs = x.T @ x + np.diag(penalty)
    solution = np.linalg.solve(lhs, x.T @ y)
    avg = solution[0]
    # Re-center defense to mean zero (offense compensates) for interpretable values.
    offense = solution[1:1+n].copy()
    defense = solution[1+n:1+2*n].copy()
    offset = float(np.mean(defense))
    offense -= offset
    defense -= offset
    records = []
    for tid, k in index.items():
        count = int(counts[k])
        good = count >= min_games
        o = float(avg + offense[k]) if good else np.nan
        d = float(avg + defense[k]) if good else np.nan
        records.append({"Team ID":tid, "adj_o":o, "adj_d":d,
                        "adj_em":o-d if good else np.nan,
                        "games_used":count,"league_games":len(frame),
                        "method":"Regularized two-way opponent-adjusted, provisional"})
    return pd.DataFrame(records, columns=columns)

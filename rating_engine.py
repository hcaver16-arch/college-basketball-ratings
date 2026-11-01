"""Shared rating math used by Streamlit and GitHub Actions."""
import pandas as pd
import numpy as np
def calculate_power(history: pd.DataFrame):
    """Regularized least squares: margin = rating(home) - rating(away) + location.

    Estimate neutral-court team point strengths from completed games, limited to
    rows with two valid ESPN team IDs and final numeric scores. Fixed HCA is an
    explicit simplifying assumption; a later version should estimate it.
    """
    empty = pd.DataFrame(columns=["Team ID", "Team", "Power", "Games", "Win %"])
    if history.empty:
        return empty, {"games": 0, "teams": 0}
    games = history[(history["Status"] == "Final") & history["Home score"].notna() & history["Away score"].notna()].copy()
    # Normalize before set/index construction; mixed numeric/string IDs otherwise raise KeyError.
    for column in ("Home ID", "Away ID"):
        games[column] = games[column].astype("string").str.strip()
    games = games[games["Home ID"].notna() & games["Away ID"].notna()]
    games = games[(games["Home ID"] != "") & (games["Away ID"] != "") &
                  (~games["Home ID"].str.lower().isin(["nan", "none", "<na>"])) &
                  (~games["Away ID"].str.lower().isin(["nan", "none", "<na>"])) &
                  (games["Home ID"] != games["Away ID"])].copy()
    # Venue values remain unchanged for recognized Home/Neutral games.
    # Unknown values are counted and excluded rather than silently receiving HCA.
    games["Venue"] = games["Venue"].astype("string").str.strip()
    unknown_venues = int((~games["Venue"].isin(["Home", "Neutral"])).sum())
    games = games[games["Venue"].isin(["Home", "Neutral"])].copy()
    games = games.drop_duplicates(subset="Game ID")
    if len(games) < 20:
        return empty, {"games": int(len(games)), "teams": 0, "unknown_venue_games": unknown_venues}
    tids = sorted(set(games["Home ID"]).union(games["Away ID"]))
    n = len(tids)
    index = {tid: i for i, tid in enumerate(tids)}
    mat = np.zeros((n, n), dtype=float)
    vec = np.zeros(n, dtype=float)
    played = np.zeros(n, dtype=int)
    wins = np.zeros(n, dtype=int)
    labels = {}
    # DataFrame column names contain spaces; iterrows keeps labels intact.
    for _, g in games.iterrows():
        hi, ai = index[str(g["Home ID"])], index[str(g["Away ID"])]
        # Cap blowouts to keep unusual games from dominating the fitted ratings.
        diff = float(np.clip(float(g["Home score"]) - float(g["Away score"]), -40, 40))
        margin = diff - (0.0 if g["Venue"] == "Neutral" else 3.0)
        mat[hi, hi] += 1; mat[ai, ai] += 1
        mat[hi, ai] -= 1; mat[ai, hi] -= 1
        vec[hi] += margin; vec[ai] -= margin
        played[hi] += 1; played[ai] += 1
        wins[hi] += int(diff > 0); wins[ai] += int(diff < 0)
        labels[str(g["Home ID"])] = str(g["Home"])
        labels[str(g["Away ID"])] = str(g["Away"])
    # Ridge shrinkage (prior rating zero), produces stable results even in
    # disconnected schedule components. Remove mean to keep readable scale.
    ridge = 8.0
    fit = np.linalg.solve(mat + ridge * np.eye(n), vec)
    fit -= np.mean(fit)
    result = pd.DataFrame({"Team ID": tids, "Team": [labels.get(tid, tid) for tid in tids], "Power": np.round(fit, 2), "Games": played, "Win %": np.round(100 * wins / np.maximum(played, 1), 1)})
    return result, {"games": len(games), "teams": n, "unknown_venue_games": unknown_venues}

def blending_weight(games: int):
    # Phaseout is deliberately bounded, even for a schedule with weak competition.
    anchors = [(0, 0), (5, .35), (10, .65), (15, .85), (20, .95), (25, 1.0)]
    for (g0, w0), (g1, w1) in zip(anchors, anchors[1:]):
        if games <= g1:
            return w0 + (w1 - w0) * (games - g0) / (g1 - g0)
    return 1.0

def make_combined(preseason: pd.DataFrame, current: pd.DataFrame, effects: dict):
    out = preseason[["Team ID", "Team", "Power"]].rename(columns={"Power":"Prior team rating"}).copy()
    out = out.merge(current[["Team ID", "Power", "Games"]].rename(columns={"Power": "On-court rating", "Games": "Games played"}), on="Team ID", how="left")
    out["Games played"] = out["Games played"].fillna(0).astype(int)
    out["Preseason roster adjustment"] = out["Team ID"].map(effects).fillna(0.0)
    out["Preseason rating"] = out["Prior team rating"] + out["Preseason roster adjustment"]
    out["On-court weight"] = out["Games played"].apply(blending_weight)
    out["Preseason weight"] = 1 - out["On-court weight"]
    out["Current power"] = (out["Preseason weight"] * out["Preseason rating"] +
                            out["On-court weight"] * out["On-court rating"].fillna(0.0))
    # Teams with in-season games but absent from last season get a neutral prior.
    new = current[~current["Team ID"].isin(out["Team ID"])].copy()
    if not new.empty:
        more = pd.DataFrame({"Team ID":new["Team ID"],"Team":new["Team"],"Prior team rating":0.,
            "On-court rating":new["Power"],"Games played":new["Games"].astype(int),
            "Preseason roster adjustment":new["Team ID"].map(effects).fillna(0.)})
        more["Preseason rating"] = more["Preseason roster adjustment"]
        more["On-court weight"] = more["Games played"].apply(blending_weight)
        more["Preseason weight"] = 1 - more["On-court weight"]
        more["Current power"] = more["Preseason weight"] * more["Preseason rating"] + more["On-court weight"] * more["On-court rating"]
        out = pd.concat([out, more], ignore_index=True)
    out["Rating change"] = out["Current power"] - out["Preseason rating"]
    return out.sort_values("Current power", ascending=False).reset_index(drop=True)

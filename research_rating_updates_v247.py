"""V247 read-only production rating-update audit, using saved dated snapshots.

This measures observed rating changes and their algebraic decomposition; it
does not claim that an individual game *caused* a specific rating movement.
No recomputation, model tuning, or modification of official ratings.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
SPORTS = ("mens-college-basketball", "womens-college-basketball")
REQUIRED_SNAP = {"Snapshot date", "Team ID", "Current power", "Preseason rating",
                 "On-court rating", "Games played", "Preseason weight"}
REQUIRED_GAME = {"Game ID", "Date", "Status", "Home ID", "Away ID", "Home score",
                 "Away score", "Venue"}
TOL = 0.06


def read(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Missing archived evidence: {path}")
    return pd.read_csv(path, compression="gzip", dtype={"Team ID": str,
        "Home ID": str, "Away ID": str, "Game ID": str})


def validate_snapshots(raw: pd.DataFrame) -> pd.DataFrame:
    if missing := REQUIRED_SNAP-set(raw):
        raise ValueError(f"Snapshot fields missing: {sorted(missing)}")
    d = raw.copy()
    d["Snapshot date"] = pd.to_datetime(d["Snapshot date"], errors="raise").dt.date
    d["Team ID"] = d["Team ID"].astype("string").str.strip()
    if d["Team ID"].isna().any() or d["Team ID"].eq("").any() or d.duplicated(
            ["Snapshot date", "Team ID"]).any():
        raise ValueError("Duplicate/missing team-date snapshots")
    for col in REQUIRED_SNAP-{"Snapshot date", "Team ID"}:
        d[col] = pd.to_numeric(d[col], errors="coerce")
    if d[list(REQUIRED_SNAP-{"Snapshot date", "Team ID", "On-court rating"})].isna().any().any():
        raise ValueError("Snapshot has missing numeric data")
    if not d["Preseason weight"].between(0, 1).all():
        raise ValueError("Invalid preseason weight")
    # make_combined sets missing current on-court strength to zero for blending.
    predicted = (d["Preseason weight"]*d["Preseason rating"] +
                 (1-d["Preseason weight"])*d["On-court rating"].fillna(0))
    mismatch = (predicted-d["Current power"]).abs()
    # Teams with no current games have an empty on-court rating; verify with zero.
    if (mismatch > TOL).any():
        raise ValueError(f"Snapshot blend identity failed on {int((mismatch>TOL).sum())} rows")
    return d.sort_values(["Snapshot date", "Team ID"])


def validate_games(raw: pd.DataFrame) -> pd.DataFrame:
    if missing := REQUIRED_GAME-set(raw):
        raise ValueError(f"Game fields missing: {sorted(missing)}")
    d = raw.copy()
    d = d[d["Status"].eq("Final")].copy()
    d["Date"] = pd.to_datetime(d["Date"], errors="raise").dt.date
    for c in ("Home ID", "Away ID", "Game ID"):
        d[c] = d[c].astype("string").str.strip()
    d["Home score"] = pd.to_numeric(d["Home score"], errors="coerce")
    d["Away score"] = pd.to_numeric(d["Away score"], errors="coerce")
    d = d.dropna(subset=["Home ID", "Away ID", "Game ID", "Home score", "Away score"])
    d = d[d["Venue"].isin(("Home", "Neutral"))]
    if d["Game ID"].duplicated().any():
        raise ValueError("Duplicate final game IDs")
    d["margin"] = d["Home score"]-d["Away score"]
    d["capped_margin"] = d["margin"].clip(-40, 40)
    d["cap_truncated"] = d["margin"].abs() > 40
    return d


def transitions(snaps: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    days = sorted(snaps["Snapshot date"].unique())
    if len(days) < 2:
        raise ValueError("At least two archived snapshot dates required")
    pieces = []
    for previous, current in zip(days, days[1:]):
        left = snaps[snaps["Snapshot date"].eq(previous)].set_index("Team ID")
        right = snaps[snaps["Snapshot date"].eq(current)].set_index("Team ID")
        both = left.join(right, lsuffix="_before", rsuffix="_after", how="inner")
        if both.empty:
            continue
        w0 = both["Preseason weight_before"].to_numpy(float)
        w1 = both["Preseason weight_after"].to_numpy(float)
        prior0 = both["Preseason rating_before"].to_numpy(float)
        prior1 = both["Preseason rating_after"].to_numpy(float)
        court0 = both["On-court rating_before"].fillna(0).to_numpy(float)
        court1 = both["On-court rating_after"].fillna(0).to_numpy(float)
        # Exact telescoping identity (including changes to prior if any):
        # Δ = w0 Δprior + (1-w0) Δcourt + Δw (prior1-court1)
        prior_effect = w0*(prior1-prior0)
        court_effect = (1-w0)*(court1-court0)
        weight_effect = (w1-w0)*(prior1-court1)
        change = both["Current power_after"].to_numpy(float)-both["Current power_before"].to_numpy(float)
        if not np.allclose(change, prior_effect+court_effect+weight_effect, atol=2*TOL):
            raise ValueError("Rating movement decomposition failed")
        period = games[(games["Date"] > previous) & (games["Date"] <= current)]
        counts = pd.concat([period["Home ID"], period["Away ID"]]).value_counts()
        row = pd.DataFrame({"team_id": both.index.astype(str),
            "previous_date": str(previous), "snapshot_date": str(current),
            "rating_before": both["Current power_before"].to_numpy(float),
            "rating_after": both["Current power_after"].to_numpy(float),
            "rating_change": change, "prior_component": prior_effect,
            "on_court_component": court_effect, "blend_weight_component": weight_effect,
            "games_before": both["Games played_before"].to_numpy(float),
            "games_after": both["Games played_after"].to_numpy(float),
            "preseason_weight_before": w0, "preseason_weight_after": w1,
            "opponent_schedule_games": both.index.astype(str).map(counts).fillna(0).astype(int)})
        row["games_delta"] = row["games_after"]-row["games_before"]
        row["did_not_play"] = row["opponent_schedule_games"].eq(0)
        row["schedule_games_disagree"] = row["games_delta"].ne(row["opponent_schedule_games"])
        pieces.append(row)
    if not pieces:
        raise ValueError("No comparable snapshots")
    return pd.concat(pieces, ignore_index=True)


def game_surprises(snaps: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    # Previous available snapshot, strictly before game day; only one final
    # per team per day to avoid pretending sequential same-day updates exist.
    records = []
    dates = sorted(snaps["Snapshot date"].unique())
    for day, group in games.groupby("Date"):
        prior_days = [d for d in dates if d < day]
        if not prior_days:
            continue
        previous = prior_days[-1]
        strength = snaps[snaps["Snapshot date"].eq(previous)].set_index("Team ID")["Current power"]
        for _, g in group.iterrows():
            home, away = str(g["Home ID"]), str(g["Away ID"])
            if home not in strength or away not in strength:
                continue
            expected = float(strength[home]-strength[away]+(3 if g["Venue"] == "Home" else 0))
            records.append({"game_id": str(g["Game ID"]), "day": str(day),
                "last_snapshot": str(previous), "home_id": home, "away_id": away,
                "expected_margin_from_saved_ratings": expected,
                "actual_margin": float(g["margin"]),
                "capped_margin": float(g["capped_margin"]),
                "margin_surprise": float(g["margin"]-expected),
                "capped_margin_surprise": float(g["capped_margin"]-expected),
                "blowout_over_40": bool(g["cap_truncated"]),
                "prior_home_strength": float(strength[home]),
                "prior_away_strength": float(strength[away])})
    return pd.DataFrame(records)


def summarize(movements: pd.DataFrame, surprises: pd.DataFrame) -> dict:
    no_game = movements[movements["did_not_play"]]
    played = movements[~movements["did_not_play"]]
    def group(x):
        return {"team_transitions": len(x),
                "mean_absolute_rating_change": round(float(x["rating_change"].abs().mean()), 4) if len(x) else None,
                "mean_signed_rating_change": round(float(x["rating_change"].mean()), 4) if len(x) else None,
                "mean_abs_on_court_component": round(float(x["on_court_component"].abs().mean()), 4) if len(x) else None,
                "mean_abs_blend_component": round(float(x["blend_weight_component"].abs().mean()), 4) if len(x) else None}
    return {"snapshot_transitions": len(movements), "played": group(played),
            "did_not_play": group(no_game),
            "games_delta_mismatch_rows": int(movements["schedule_games_disagree"].sum()),
            "surprise_games": len(surprises),
            "blowout_over_40_games": int(surprises["blowout_over_40"].sum()) if len(surprises) else 0,
            "limitations": [
                "Daily snapshots are whole-league simultaneous re-fits; changes on no-game days can reflect other teams' results, not necessarily bugs.",
                "Saved rating snapshots can skip dates; schedule games and games-played deltas are separately reported.",
                "Game surprises use the latest archived snapshot strictly before the game date; not immutable forecast records.",
                "The 40-point cap limits the contribution of blowouts to the fitted on-court rating.",
                "Venue classification is from ESPN and not independently verified.",
                "Decomposition is an algebraic identity, not a causal attribution to a specific game."]}


def run(root: Path, out: Path) -> dict:
    result = {"version": 247, "status": "RESEARCH_ONLY_NOT_DEPLOYED",
              "production_changed": False, "divisions": {}}
    out.mkdir(parents=True, exist_ok=True)
    for sport in SPORTS:
        base = root/"data/ratings"/sport
        snaps = validate_snapshots(read(base/"history.csv.gz"))
        games = validate_games(read(base/"season_2026-27.csv.gz"))
        moves = transitions(snaps, games)
        surprises = game_surprises(snaps, games)
        summary = summarize(moves, surprises)
        result["divisions"][sport] = summary
        moves.to_csv(out/f"{sport}_rating_transitions.csv", index=False)
        surprises.to_csv(out/f"{sport}_game_surprises.csv", index=False)
    (out/"summary.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--out", type=Path, default=ROOT/"data/research_rating_updates_v247")
    a = p.parse_args()
    run(a.root.resolve(), a.out.resolve())

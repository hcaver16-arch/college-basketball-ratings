"""V229: research-only preseason-anchor transition study.

No production ratings, weights, or immutable forecasts are changed.

Compare on identical early-2026-27 verified-D1 games:
  - prior_only: 2025-26 completed-game power, known before 2026-27
  - legacy_replay: existing zero-centered current-only ridge plus 0/5/10/...
                   blend weights, recomputed using preceding *dates only*
  - anchored_ridge8: current-season margins fitted WITH the historical power
                     vector as the ridge reference rather than zero.

A match on day D only trains on final games dated BEFORE D, never any
same-day outcomes. This is a conservative day-before replay, NOT an actual
time-stamped prospective forecast. The existing 2026-27 season archive is
incomplete or potentially stale and has non-D1 opponents; report coverage.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path

import numpy as np
import pandas as pd

from rating_engine import calculate_power, blending_weight

SPORTS = ("mens-college-basketball", "womens-college-basketball")
ROOT = Path(__file__).resolve().parent
CAP = 40.0
HOME_ADVANTAGE = 3.0
RIDGE = 8.0
MIN_EVIDENCE_GAMES = 100
COLUMNS = ("Game ID", "Date", "Home ID", "Away ID", "Home",
           "Away", "Home score", "Away score", "Status", "Venue")


def normalize(raw: pd.DataFrame, label: str) -> pd.DataFrame:
    if not set(COLUMNS).issubset(raw.columns):
        raise ValueError(f"{label}: season archive lacks necessary columns")
    g = raw.copy()
    for field in ("Game ID", "Home ID", "Away ID"):
        g[field] = g[field].astype("string").str.strip()
    g = g[g["Status"].eq("Final")]
    g = g.dropna(subset=["Game ID", "Home ID", "Away ID"])
    g = g[g["Game ID"].ne("") & g["Home ID"].ne("") & g["Away ID"].ne("")]
    g = g[g["Home ID"] != g["Away ID"]]
    g["Day"] = pd.to_datetime(g["Date"], errors="coerce").dt.date
    g["Home score"] = pd.to_numeric(g["Home score"], errors="coerce")
    g["Away score"] = pd.to_numeric(g["Away score"], errors="coerce")
    g = g.dropna(subset=["Day", "Home score", "Away score"])
    g = g[g["Venue"].isin(["Home", "Neutral"])]
    g = g[(g["Home score"] >= 0) & (g["Away score"] >= 0)]
    if g["Game ID"].duplicated().any():
        # Failing is safer than silently double-counting a game in the fit.
        raise ValueError(f"{label}: duplicate completed Game ID")
    return g.sort_values(["Day", "Game ID"]).reset_index(drop=True)


def historical_prior(prior_games: pd.DataFrame) -> dict[str, float]:
    fit, details = calculate_power(prior_games)
    if fit.empty or details["games"] < 1000:
        raise ValueError("Insufficient verified previous-season scoring-margin data")
    return dict(zip(fit["Team ID"].astype(str), fit["Power"].astype(float)))


def legacy_replay(prior: dict, past: pd.DataFrame):
    """Replicate zero-prior in-season fitting and make_combined weight math."""
    if past.empty:
        return dict(prior), {}
    fit, _ = calculate_power(past)
    raw = dict(zip(fit["Team ID"].astype(str), fit["Power"].astype(float)))
    counts = dict(zip(fit["Team ID"].astype(str), fit["Games"].astype(int)))
    # As in production, before 20 total final games the fitted on-court
    # table (and its Games counts) is empty; teams retain the preseason fit.
    result = {}
    for team_id in set(prior) | set(counts):
        p = prior.get(team_id, 0.0)
        # A pre-20-game fit is absent and production make_combined uses
        # zero filled on-court ratings if that team has games.
        weight = blending_weight(counts.get(team_id, 0))
        result[team_id] = (1 - weight) * p + weight * raw.get(team_id, 0.0)
    return result, counts


def anchored_ridge(prior: dict[str, float], past: pd.DataFrame,
                   ridge: float = RIDGE) -> dict[str, float]:
    """MAP-style ridge fit to a *fixed preseason power vector*.

    Solve (L + λI)r = b + λr_pre, where L is the game-opponent
    graph Laplacian. When there are no games, r == r_pre exactly.
    No information from held-out results enters this solution.
    """
    if not np.isfinite(ridge) or ridge <= 0:
        raise ValueError("ridge must be positive and finite")
    if past.empty:
        return dict(prior)
    teams = sorted(set(prior) | set(past["Home ID"].astype(str)) |
                   set(past["Away ID"].astype(str)))
    loc = {team: index for index, team in enumerate(teams)}
    n = len(teams)
    values = np.array([prior.get(team, 0.0) for team in teams], dtype=float)
    matrix = np.eye(n, dtype=float) * ridge
    right = ridge * values
    for game in past.to_dict("records"):
        h, a = loc[str(game["Home ID"])], loc[str(game["Away ID"])]
        diff = float(np.clip(game["Home score"] - game["Away score"],
                             -CAP, CAP))
        adjusted = diff - (0.0 if game["Venue"] == "Neutral"
                            else HOME_ADVANTAGE)
        matrix[h, h] += 1.0
        matrix[a, a] += 1.0
        matrix[h, a] -= 1.0
        matrix[a, h] -= 1.0
        right[h] += adjusted
        right[a] -= adjusted
    solution = np.linalg.solve(matrix, right)
    if not np.all(np.isfinite(solution)):
        raise ValueError("Nonfinite anchored power fit")
    return dict(zip(teams, solution))


def _prediction(home_id, away_id, site, ratings):
    if home_id not in ratings or away_id not in ratings:
        return None
    h = ratings[home_id]
    a = ratings[away_id]
    if not np.isfinite(h) or not np.isfinite(a):
        return None
    return float(h - a + (0 if site == "Neutral" else HOME_ADVANTAGE))


def metrics(rows, key):
    if not rows:
        return {"games": 0, "mae": None, "rmse": None,
                "winner_accuracy": None, "bias": None}
    a = np.array([x["actual_margin"] for x in rows], dtype=float)
    p = np.array([x[key] for x in rows], dtype=float)
    margin_valid = (a != 0) & (p != 0)
    err = a - p
    return {
        "games": len(rows),
        "mae": round(float(np.abs(err).mean()), 4),
        "rmse": round(float(np.sqrt((err**2).mean())), 4),
        "winner_accuracy": (round(float((np.sign(a[margin_valid]) ==
                                         np.sign(p[margin_valid])).mean()), 4)
                            if margin_valid.any() else None),
        "bias": round(float(err.mean()), 4),
    }


def evaluate(prior_games: pd.DataFrame, current_games: pd.DataFrame,
             d1_ids: set[str], asof: date, team_watch_id="356"):
    """Day-before replay. Same held-out games for all three candidates."""
    prior = historical_prior(normalize(prior_games, "previous-season"))
    current = normalize(current_games, "current-season")
    current = current[(current["Day"] >= date(2026, 11, 1)) &
                      (current["Day"] <= asof)].copy()
    ids = set(map(str, d1_ids))
    if len(ids) < 200:
        raise ValueError("D1 membership source incomplete; refusing D1 accuracy claims")
    if current.empty:
        return pd.DataFrame(), {"status": "NO_SAVED_FINALS"}
    rows = []
    date_report = []
    for target_day in sorted(current["Day"].unique()):
        # IMPORTANT: all games from the target day are held out, even
        # earlier tipoffs; live production may know more games than this.
        train = current[current["Day"] < target_day]
        target = current[(current["Day"] == target_day) &
                         current["Home ID"].astype(str).isin(ids) &
                         current["Away ID"].astype(str).isin(ids)]
        legacy, counts = legacy_replay(prior, train)
        anchored = anchored_ridge(prior, train)
        last_train = str(max(train["Day"])) if len(train) else None
        date_report.append({
            "target_day": str(target_day),
            "games_before_day": len(train),
            "latest_used_training_day": last_train,
            "d1_targets": len(target),
        })
        assert last_train is None or last_train < str(target_day)
        for _, game in target.iterrows():
            h, a = str(game["Home ID"]), str(game["Away ID"])
            # No invented zero-prior ratings for unrepresented historical
            # teams. All three variants must use identical game coverage.
            if h not in prior or a not in prior:
                continue
            rec = {
                "game_id": str(game["Game ID"]),
                "day": str(target_day), "home_id": h, "away_id": a,
                "home_team": str(game["Home"]), "away_team": str(game["Away"]),
                "neutral": game["Venue"] == "Neutral",
                "actual_margin": float(game["Home score"] - game["Away score"]),
                "prior_only": _prediction(h, a, game["Venue"], prior),
                "legacy_replay": _prediction(h, a, game["Venue"], legacy),
                "anchored_ridge8": _prediction(h, a, game["Venue"], anchored),
                "games_before_day": len(train),
                "latest_training_day": last_train,
                "home_gp_before": int(counts.get(h, 0)),
                "away_gp_before": int(counts.get(a, 0)),
            }
            if all(rec[k] is not None for k in
                   ("prior_only", "legacy_replay", "anchored_ridge8")):
                rows.append(rec)
    out = pd.DataFrame(rows)
    samples = out.to_dict("records")
    keys = ("prior_only", "legacy_replay", "anchored_ridge8")
    group = {k: metrics(samples, k) for k in keys}
    buckets = {}
    if not out.empty:
        for label, f in (
            ("both_0_to_2_games", lambda d: d["home_gp_before"].le(2) &
                                            d["away_gp_before"].le(2)),
            ("either_3_plus_games", lambda d: d["home_gp_before"].ge(3) |
                                             d["away_gp_before"].ge(3)),
        ):
            segment = out.loc[f(out)].to_dict("records")
            buckets[label] = {"matched_games": len(segment),
                              **{k: metrics(segment, k) for k in keys}}
    case = {}
    # Retrospective diagnostic only: fitted after (not before) games on Nov 2.
    # Never use these retrospective ratings as "before tip" forecasts.
    if team_watch_id in prior and any(
        team_watch_id in (str(g["Home ID"]), str(g["Away ID"]))
        for _, g in current.iterrows()
    ):
        day2 = current[current["Day"] <= date(2026, 11, 2)]
        base = prior[team_watch_id]
        l, _ = legacy_replay(prior, day2)
        anchored = anchored_ridge(prior, day2)
        case = {
            "team_id": team_watch_id, "preseason_rating": round(base, 3),
            "legacy_after_nov_2": round(l[team_watch_id], 3),
            "anchored_after_nov_2": round(anchored[team_watch_id], 3),
            "legacy_delta_from_preseason": round(l[team_watch_id]-base, 3),
            "anchored_delta_from_preseason": round(anchored[team_watch_id]-base, 3),
            "caution": "Retrospective Nov 2 scores included; illustrative only, not pre-tip evidence.",
        }
    # Matched games where all models predict the same margin cannot
    # establish anything about which transition strategy is preferable.
    # Count only genuine model disagreements as information for selection.
    informative = out[
        (out["anchored_ridge8"] - out["legacy_replay"]).abs().gt(0.05)
    ] if not out.empty else out
    informative_rows = informative.to_dict("records")
    if len(informative) == 0:
        status = "NO_INFORMATIVE_MODEL_DISAGREEMENTS_YET"
    elif len(informative) < MIN_EVIDENCE_GAMES:
        status = "TOO_FEW_INFORMATIVE_MATCHUPS_FOR_MODEL_SELECTION"
    else:
        status = "EXPLORATORY_MINIMUM_REACHED_NOT_INDEPENDENT_HOLDOUT"
    report = {
        "status": status, "matched_games": len(out),
        "informative_model_disagreement_games": len(informative),
        "informative_disagreement_tolerance_points": 0.05,
        "informative_matchup_metrics": {k: metrics(informative_rows,k) for k in keys},
        "model_variants": list(keys), "all_games_on_identical_matchups": True,
        "metrics": group, "early_sample_buckets": buckets,
        "day_before_replay": date_report,
        "snapshot_source": "saved 2025-26 and 2026-27 ESPN game-result archives",
        "first_eval_date": str(min(current["Day"])), "last_eval_date": str(max(current["Day"])),
        "Illinois_diagnostic": case,
        "important_caveats": [
            "Retrospective day-before model replay, NOT immutable official pregame forecasts.",
            "A final game can enter the fit only on a later calendar day. No same-day future score leakage.",
            "The 2025-26 archive contains historical season results, but not verified point-in-time roster changes.",
            "Current-season archive freshness can lag when daily ratings workflows fail.",
            "Fresh ESPN result supplementation is a research-only read; no saved production ratings or forecasts are changed.",
            "Fresh scoreboard discovery covers no more than the latest 14 dates; earlier saved archive gaps remain possible.",
            "D1 membership uses current ESPN group-50, not a historical NCAA eligibility census.",
            "Matched games with identical candidate predictions provide ZERO evidence for selecting a new blend.",
            "These 2026-27 results are an exploratory sample; hold out future unseen games for final selection.",
            "No production coefficients, model ratings or original first forecasts were changed.",
        ],
    }
    if not out.empty:
        report["delta_mae_anchor_minus_legacy"] = round(
            group["anchored_ridge8"]["mae"] - group["legacy_replay"]["mae"], 4
        )
    return out, report


def fresh_scoreboard_finals(sport: str, asof: date) -> pd.DataFrame:
    """Independent dated ESPN feed sample; never modifies saved production input.

    Only fetch at most the last 14 calendar days; research output discloses
    that earlier season gaps in the saved archive are not independently filled.
    """
    from daily_ratings import request_date, COLUMNS as ESPN_COLS
    first = max(date(2026,11,1), asof - timedelta(days=13))
    days = [first + timedelta(days=i) for i in range((asof-first).days+1)]
    out = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {pool.submit(request_date, sport, day): day for day in days}
        for future in as_completed(pending):
            try:
                out.extend(future.result())
            except Exception as exc:
                raise RuntimeError(f"{sport}: failed complete fresh day {pending[future]}: {exc}") from exc
    return pd.DataFrame(out, columns=ESPN_COLS)


def supplement_saved_finals(saved: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    """A reproducible research view of latest ESPN finals; no production write."""
    if fresh.empty:
        return saved.copy()
    latest = pd.concat([saved, fresh], ignore_index=True)
    # Date-scoped ESPN feeds may overlap or a game may be corrected.
    latest["Game ID"] = latest["Game ID"].astype(str)
    return latest.drop_duplicates("Game ID", keep="last").reset_index(drop=True)


def research_main(root: Path, output: Path, asof: date = None,
                  d1_lookup=None, refresh_current=False):
    from reliability_v99 import fetch_d1_membership
    asof = asof or datetime.now(timezone.utc).date()
    reports = {}
    outputs = {}
    for sport in SPORTS:
        base = root / "data" / "ratings" / sport
        old = pd.read_csv(base / "history_2025-26.csv.gz",
                          dtype={"Game ID": str, "Home ID": str, "Away ID": str})
        current = pd.read_csv(base / "season_2026-27.csv.gz",
                              dtype={"Game ID": str, "Home ID": str, "Away ID": str})
        ids = d1_lookup(sport) if d1_lookup is not None else fetch_d1_membership(sport)
        saved_ids = set(normalize(current, "saved-current")["Game ID"].astype(str))
        if refresh_current:
            fresh = fresh_scoreboard_finals(sport, asof)
            merged = supplement_saved_finals(current, fresh)
            fresh_final_ids = set(normalize(fresh, "fresh-source")["Game ID"].astype(str))
            matched, report = evaluate(old, merged, ids, asof)
            report["fresh_espn_final_game_ids"] = len(fresh_final_ids)
            report["new_espn_final_game_ids_not_in_saved_archive"] = len(fresh_final_ids - saved_ids)
            report["fresh_scoreboard_days_retrieved"] = min(14, (asof-date(2026,11,1)).days+1)
            report["current_archive_provenance"] = "saved current-season archive supplemented with live ESPN scoreboard finals"
            outputs[sport + "_fresh_finals"] = fresh.loc[fresh["Status"].eq("Final")].copy()
        else:
            matched, report = evaluate(old, current, ids, asof)
            report["current_archive_provenance"] = "saved current-season archive only"
        meta = json.loads((base / "status.json").read_text())
        report["saved_ratings_snapshot_date"] = meta.get("snapshot_date")
        report["saved_ratings_updated_utc"] = meta.get("updated_utc")
        reports[sport] = report
        outputs[sport + "_day_before_predictions"] = matched
    output.mkdir(parents=True, exist_ok=True)
    for label, frame in outputs.items():
        frame.to_csv(output / f"{label}.csv", index=False)
    summary = {
        "version": 229, "generated_utc": datetime.now(timezone.utc).isoformat(),
        "asof_date": str(asof), "purpose": "RESEARCH_ONLY_NEVER_UPDATE_OFFICIAL_MODEL",
        "divisions": reports,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "data" / "research_prior_transition_v229")
    parser.add_argument("--refresh-current", action="store_true",
                        help="Add latest ESPN final scores to a research copy only; saves a source snapshot.")
    args = parser.parse_args()
    research_main(args.root, args.out, refresh_current=args.refresh_current)

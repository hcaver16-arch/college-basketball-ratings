"""V209: read-only cross-division *research* projections.

Applies only to exactly one verified Division I team and one opponent outside
Courtside's VERIFIED Division I membership set. An absent D1 membership is
not definitive evidence of Division II/III/NAIA classification.
The empirical prior comes ONLY from 2025-26 historical completed results.
No current season results, current game score, odds or player characteristics.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from datetime import date
import json
import math

ROOT=Path(__file__).resolve().parent
MAX_SOURCE_AGE_SEASONS=2
REQUIRED_SAMPLE=30
HCA=3.0


@lru_cache(maxsize=4)
def load_cross_division_calibration(sport: str):
    if sport not in ("mens-college-basketball","womens-college-basketball"):
        return None
    path=ROOT/"data"/"cross_division"/f"{sport}_2025-26.json"
    try:
        obj=json.loads(path.read_text())
        if (obj.get("source_season")!="2025-26"
            or obj.get("sport")!=sport
            or obj.get("model_version")!="v209_empirical_prior_v1"
            or int(obj.get("training_games",0))<REQUIRED_SAMPLE
            or not math.isfinite(float(obj.get("pooled_non_d1_rating")))):
            return None
        if obj.get("source_cutoff_utc","") > "2026-11-01T00:00:00Z":
            return None
        return obj
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):
        return None


def estimate(game, ratings, verified_d1_ids, calibration):
    """Return research projection; None if DI membership/rating is uncertain.

    Rating scale is the existing D1 power scale. The non-D1 pool is the median
    implied score-based strength across *last-season* D1 vs unverified team
    games. Team-specific estimates are ridge-shrunk toward that pool.
    """
    if not isinstance(calibration,dict):
        return None
    if calibration.get("model_version")!="v209_empirical_prior_v1":
        return None
    if int(calibration.get("training_games") or 0)<REQUIRED_SAMPLE:
        return None
    home,away=str(game.get("Home ID","")),str(game.get("Away ID",""))
    d1={str(x) for x in verified_d1_ids}
    if (home in d1)==(away in d1) or not home or not away or home==away:
        return None
    di=home if home in d1 else away
    outside=away if home in d1 else home
    try:
        d1rating=float(ratings[di])
        pool=float(calibration["pooled_non_d1_rating"])
    except (KeyError,ValueError,TypeError):
        return None
    if not math.isfinite(d1rating) or not math.isfinite(pool) or abs(pool)>150:
        return None
    if game.get("Venue") not in ("Home","Neutral"):
        return None
    samples=calibration.get("opponents") or {}
    item=samples.get(outside) or {}
    try:
        evidence=max(0,int(item.get("games",0)))
        other=float(item.get("shrunk_rating",pool))
    except (TypeError,ValueError):
        other=pool
        evidence=0
    if not math.isfinite(other):
        other=pool
        evidence=0
    # Keep the model explicitly separate: non-DI strength never enters D1
    # rating tables or the normal game_projection() engine.
    home_rating=d1rating if di==home else other
    away_rating=d1rating if di==away else other
    margin=home_rating-away_rating+(0 if game["Venue"]=="Neutral" else HCA)
    if not math.isfinite(margin):
        return None
    # No confidence % or probability without out-of-sample calibration.
    favorite=game.get("Home") if margin>=0 else game.get("Away")
    return {
        "home_margin":round(margin,1),
        "favorite":str(favorite),
        "spread":round(abs(margin),1),
        "outside_id":outside,
        "outside_team":str(game.get("Away") if outside==away else game.get("Home")),
        "outside_games":evidence,
        "history_games":int(calibration["training_games"]),
        "history_source":"2025–26 ESPN completed games",
        "method":"team-history shrinkage" if evidence else "pooled cross-division prior",
        "confidence":"Low",
        "note":"Experimental cross-division estimate; not betting odds or a locked pregame prediction",
    }


def line_for_game(projection):
    if not projection:
        return "No verified cross-DI estimate"
    return f"{projection['favorite']} -{projection['spread']:.1f}"

"""V206 live matchup helpers; no changes to the prediction or rating engines.

A scoreboard score/clock is live ESPN game state, NOT an in-game probability.
A historical forecast is only called "locked pregame" when V97 recorded it
at least 30 minutes before scheduled tipoff for the exact teams and fixture.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from math import erf, sqrt, isfinite
from pathlib import Path
import re


_CLOCK = re.compile(r"^(?:[0-5]?\d|[0-9]):[0-5]\d$")


def _valid_text(value):
    return value.strip() if isinstance(value, str) and value.strip() not in ("None", "nan", "NaN") else ""


def espn_progress(event, competition, status):
    """Only use explicit live status fields; no synthesized clock or period."""
    if status != "Live":
        return {"Game period": None, "Game clock": None, "Game phase": None}
    blocks = [event.get("status") or {}, competition.get("status") or {}]
    state = next((r for r in blocks if isinstance(r, dict) and r), {})
    clock = next((_valid_text(r.get("displayClock")) for r in blocks
                  if isinstance(r, dict) and _valid_text(r.get("displayClock"))), "")
    if not _CLOCK.fullmatch(clock):
        clock = ""
    phase = ""
    for r in blocks:
        if not isinstance(r, dict):
            continue
        t = r.get("type") or {}
        candidates = (t.get("shortDetail"), t.get("detail"), r.get("shortDetail"), r.get("detail"))
        if any("half" in str(label).casefold() and "halftime" in str(label).casefold() for label in candidates if label):
            phase = "Halftime"
            break
    period = next((r.get("period") for r in blocks if isinstance(r, dict) and r.get("period") is not None), None)
    if not phase:
        try:
            i = int(period)
        except (TypeError, ValueError):
            i = 0
        if i == 1:
            phase = "1st half"
        elif i == 2:
            phase = "2nd half"
        elif i == 3:
            phase = "OT"
        elif 4 <= i <= 12:
            phase = f"{i-2}OT"
    if phase == "Halftime":
        clock = ""
    return {"Game period": str(period) if period is not None else None,
            "Game clock": clock or None,
            "Game phase": phase or None}


def progress_label(game):
    """Resilient header label; no fictitious remaining time."""
    status = str(game.get("Status") or "Scheduled")
    if status != "Live":
        return "Final" if status == "Final" else "Upcoming"
    phase = _valid_text(game.get("Game phase"))
    clock = _valid_text(game.get("Game clock"))
    if phase == "Halftime":
        return phase
    if phase and clock:
        return f"{phase} · {clock}"
    if phase:
        return phase
    if clock:
        return f"Live · {clock}"
    return "Live · game clock unavailable"


def score_pair(game):
    """Return both team scores only when both are verifiably numeric."""
    try:
        a, h = float(game.get("Away score")), float(game.get("Home score"))
        if not isfinite(a) or not isfinite(h) or a < 0 or h < 0:
            return None
        if not a.is_integer() or not h.is_integer():
            return None
        return (int(a), int(h))
    except (TypeError, ValueError):
        return None


def _utc(text):
    try:
        t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def locked_pregame_forecast(game, league, root=None):
    """Read the *first recorded* V97 forecast only; no backfill or live reweighting.

    Corroborates IDs, league, game ID, and the pretip creation timestamp.
    Missing/invalid journal rows return None rather than a misleading "pregame"
    probability. Does not mutate the journal or use game outcome.
    """
    path = (Path(root) if root is not None else Path(__file__).resolve().parent) / "data/prospective/2026-27/forecasts.csv"
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8", newline="") as fd:
            rows = csv.DictReader(fd)
            for r in rows:
                if (str(r.get("game_id")) != str(game.get("Game ID"))
                        or str(r.get("division")) != str(league)
                        or r.get("model_id") != "official_saved_v97"):
                    continue
                if (str(r.get("home_id")) != str(game.get("Home ID"))
                        or str(r.get("away_id")) != str(game.get("Away ID"))):
                    continue
                created = _utc(r.get("forecast_created_utc"))
                tipoff = _utc(r.get("game_start_utc"))
                if created is None or tipoff is None or created > tipoff - timedelta(minutes=30):
                    return None
                try:
                    margin = float(r["predicted_home_margin"])
                except (TypeError, ValueError):
                    return None
                if not isfinite(margin) or abs(margin) > 150:
                    return None
                probability = 100 * .5 * (1+erf(margin/(11*sqrt(2))))
                return {"margin": round(margin, 1), "probability": round(probability, 1),
                        "created": created.isoformat(), "source": "first V97 archived pregame prediction"}
    except (OSError, UnicodeError, csv.Error):
        return None
    return None

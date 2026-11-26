"""V260 experimental coaching evidence, never an unsourced coach-rating feed.

Catalog references from ESPN may contain assistants or no role information.
Only an EXPLICIT head-coach designation tied to one team and coach ID is
accepted; ambiguity means the coaching component stays unavailable/neutral.
Catalogs are observational snapshots, NOT verified past pretip coach history.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from urllib.parse import urlparse

import requests

SEASON = 2027
PREVIOUS = 2026
HEADERS = {"User-Agent": "Courtside shadow-model research/1.0", "Accept": "application/json"}
BASE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/"


def _id(value):
    if isinstance(value, dict):
        if value.get("id") is not None:
            return str(value["id"]).strip()
        value = value.get("$ref", "")
    value = str(value or "").strip()
    if value.isdigit():
        return value
    if not value.startswith("https://sports.core.api.espn.com/"):
        return ""
    path = urlparse(value).path.rstrip("/")
    return path.split("/")[-1] if path.split("/")[-1].isdigit() else ""


def explicitly_head_coach(item: dict) -> bool:
    if item.get("isHeadCoach") is True or item.get("headCoach") is True:
        return True
    role = item.get("position") or item.get("role") or {}
    if isinstance(role, dict):
        role = role.get("name") or role.get("displayName") or role.get("abbreviation") or ""
    return str(role).lower().strip() in ("head coach", "headcoach", "hc")


def parse_coach_items(items) -> dict:
    """Never infer head-coach status from team association or array order."""
    by_team: dict[str, list[dict]] = {}
    if not isinstance(items, list):
        raise ValueError("Coach catalog missing items array")
    for item in items:
        if not isinstance(item, dict) or not explicitly_head_coach(item):
            continue
        team = _id(item.get("team"))
        coach = _id(item)
        if not team or not coach:
            continue
        name = str(item.get("fullName") or item.get("displayName") or "").strip()
        if not name:
            continue
        by_team.setdefault(team, []).append({"coach_id": coach, "name": name})
    # Two different head-coach assignments in one season are ambiguous.
    return {team: found[0] for team, found in by_team.items()
            if len(found) == 1}


def fetch_catalog(sport: str, season: int, *, session=None) -> tuple[dict, dict]:
    if sport not in ("mens-college-basketball", "womens-college-basketball"):
        raise ValueError("Unsupported coaching sport")
    if season not in (SEASON, PREVIOUS):
        raise ValueError("Unsupported coach season")
    url = f"{BASE}{sport}/seasons/{season}/coaches"
    fetcher = session or requests
    coach_rows = []
    pages = 0
    expected = 1
    while pages < expected:
        pages += 1
        if pages > 25:
            raise ValueError("Coach index exceeds bounded page limit")
        reply = fetcher.get(url, params={"limit": 100, "page": pages},
                            headers=HEADERS, timeout=25)
        reply.raise_for_status()
        payload = reply.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("Unsupported ESPN coach catalog shape")
        coach_rows.extend(payload["items"])
        page_count = int(payload.get("pageCount", 1))
        if page_count < 1 or page_count > 25:
            raise ValueError("Invalid coach catalog pagination")
        expected = page_count
    matched = parse_coach_items(coach_rows)
    return matched, {
        "season": season, "pages": pages, "rows": len(coach_rows),
        "explicit_unique_head_coaches": len(matched),
        "source": url,
        "basis": "ESPN catalog rows with explicit head-coach designation and unique team association",
    }


def coach_continuity(sport: str, now: datetime, *, session=None):
    """Continuity signal: same head coach in 2026 and 2027, never coach skill."""
    audits = []
    try:
        old, a = fetch_catalog(sport, PREVIOUS, session=session)
        current, b = fetch_catalog(sport, SEASON, session=session)
        audits.extend([a, b])
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        return {}, {
            "status": "unavailable", "reason": str(exc)[:240],
            "observed_at_utc": now.astimezone(timezone.utc).isoformat(),
            "seasons": audits, "qualified_teams": 0,
        }
    combined = {}
    for team, latest in current.items():
        older = old.get(team)
        if older:
            combined[team] = {
                "coach_id": latest["coach_id"],
                "coach": latest["name"],
                "prior_coach_id": older["coach_id"],
                "continuity": latest["coach_id"] == older["coach_id"],
                "observed_at_utc": now.astimezone(timezone.utc).isoformat(),
                "source": b["source"],
                "prior_source": a["source"],
            }
    return combined, {
        "status": "available" if combined else "not_verified",
        "observed_at_utc": now.astimezone(timezone.utc).isoformat(),
        "seasons": audits, "qualified_teams": len(combined),
        "warning": "Coach ID continuity is not coach quality. Assistants, anonymous roles and ambiguous entries are excluded.",
    }

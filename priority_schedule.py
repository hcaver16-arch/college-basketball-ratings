"""Upcoming Division I opponent priorities, sourced from ESPN's scheduled fixtures.

Priority is an ordering hint. It never changes roster provenance or quality labels.
"""
from datetime import datetime, timedelta, timezone
import requests


def upcoming_d1_ids(sport, directory_ids, days=14, request_get=None, now=None):
    get = request_get or requests.get
    now = now or datetime.now(timezone.utc)
    priority = set()
    errors = []
    for offset in range(days + 1):
        day = (now + timedelta(days=offset)).strftime('%Y%m%d')
        try:
            res = get(f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/scoreboard',
                      params={'dates':day,'groups':'50','limit':500},timeout=30)
            res.raise_for_status()
            events=res.json().get('events',[])
            if not isinstance(events,list) or len(events)>=500:
                raise ValueError('Invalid or possibly truncated daily scoreboard')
            for event in events:
                try:
                    kickoff=datetime.fromisoformat(event['date'].replace('Z','+00:00'))
                    if not now < kickoff <= now+timedelta(days=days):continue
                    competition=(event.get('competitions') or [{}])[0]
                    ids=[str(c.get('team',{}).get('id','')) for c in competition.get('competitors',[])]
                    # Prioritize D1 teams even if opponent is non-D1; prioritize *both* when both D1.
                    priority.update(set(ids)&set(directory_ids))
                except (KeyError,ValueError,IndexError,TypeError):continue
        except (requests.RequestException,ValueError) as exc:
            errors.append(f'{day}: {exc}')
    return priority, errors

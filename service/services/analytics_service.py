"""Click analytics, entirely Redis-native: a total counter (INCR), a per-day hash (HINCRBY), top
referrers/user-agents as sorted sets (ZINCRBY), and a capped recent-clicks list (LPUSH + LTRIM) —
no separate click-events table, no aggregation query. Each of these is the Redis-idiomatic
structure for its own access pattern, which is the actual point of building Zyp: sLink pulls all
of this from a click_events SQL table with GROUP BY; here each metric has its own tiny structure
updated incrementally at write time instead.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

RECENT_CLICKS_LIMIT = 50


def _day_key(code: str) -> str:
    return f"zyp:analytics:{code}:by_day"


def _total_key(code: str) -> str:
    return f"zyp:analytics:{code}:total"


def _referrers_key(code: str) -> str:
    return f"zyp:analytics:{code}:referrers"


def _user_agents_key(code: str) -> str:
    return f"zyp:analytics:{code}:user_agents"


def _recent_key(code: str) -> str:
    return f"zyp:analytics:{code}:recent"


@dataclass
class ClickRecord:
    clicked_at: float
    referrer: str
    user_agent: str


@dataclass
class LinkAnalytics:
    total_clicks: int = 0
    clicks_by_day: dict = field(default_factory=dict)
    top_referrers: list = field(default_factory=list)
    top_user_agents: list = field(default_factory=list)
    recent_clicks: list = field(default_factory=list)


class AnalyticsService:
    def __init__(self, redis_client):
        self.redis = redis_client

    def record_click(self, code: str, referrer: str, user_agent: str) -> None:
        referrer = referrer or "direct"
        now = time.time()
        day = time.strftime("%Y-%m-%d", time.gmtime(now))

        self.redis.incr(_total_key(code))
        self.redis.hincrby(_day_key(code), day, 1)
        self.redis.zincrby(_referrers_key(code), 1, referrer)
        self.redis.zincrby(_user_agents_key(code), 1, user_agent)

        record = json.dumps({"clicked_at": now, "referrer": referrer, "user_agent": user_agent})
        self.redis.lpush(_recent_key(code), record)
        self.redis.ltrim(_recent_key(code), 0, RECENT_CLICKS_LIMIT - 1)

    def get_analytics(self, code: str) -> LinkAnalytics:
        total = int(self.redis.get(_total_key(code)) or 0)
        by_day = {k: int(v) for k, v in self.redis.hgetall(_day_key(code)).items()}
        top_referrers = [(m, int(float(s))) for m, s in self.redis.zrevrange(_referrers_key(code), 0, 9, withscores=True)]
        top_user_agents = [(m, int(float(s))) for m, s in self.redis.zrevrange(_user_agents_key(code), 0, 9, withscores=True)]
        recent_raw = self.redis.lrange(_recent_key(code), 0, RECENT_CLICKS_LIMIT - 1)
        recent = [ClickRecord(**json.loads(r)) for r in recent_raw]

        return LinkAnalytics(total_clicks=total, clicks_by_day=by_day, top_referrers=top_referrers,
                              top_user_agents=top_user_agents, recent_clicks=recent)

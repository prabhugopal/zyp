"""Fixed-window rate limiting via a Redis INCR+EXPIRE counter keyed per client per minute-window —
applied to link creation only (matches sLink's create-only rate-limit decision). This is the one
place Redis is a strictly better fit than sLink's in-memory Bucket4j/Caffeine registry: the counter
already lives in the same store as everything else, with no separate in-process bucket cache to
keep synchronized across instances.
"""

from __future__ import annotations

import time


class RateLimiter:
    def __init__(self, redis_client, limit_per_minute: int):
        self.redis = redis_client
        self.limit = limit_per_minute

    def allow(self, client_id: str) -> bool:
        window = int(time.time() // 60)
        key = f"zyp:ratelimit:{client_id}:{window}"
        count = self.redis.incr(key)
        if count == 1:
            self.redis.expire(key, 60)
        return count <= self.limit

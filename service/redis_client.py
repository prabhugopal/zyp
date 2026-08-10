"""Redis connection factory — a single choke point so services never import redis directly,
letting tests swap in fakeredis.FakeRedis without touching service code."""

from __future__ import annotations

import redis


def create_redis(url: str) -> redis.Redis:
    return redis.Redis.from_url(url, decode_responses=True)

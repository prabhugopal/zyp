"""FastAPI dependency-injection accessors. Services are constructed once in app.py's lifespan and
stashed on app.state; routes pull them via Depends() rather than importing module-level globals,
so tests can build a fresh app (and a fresh fakeredis/real-Redis client) per test with no shared
state.
"""

from __future__ import annotations

from fastapi import Request

from config import Config
from rate_limit import RateLimiter
from services.analytics_service import AnalyticsService
from services.link_service import LinkService


def get_link_service(request: Request) -> LinkService:
    return request.app.state.link_service


def get_analytics_service(request: Request) -> AnalyticsService:
    return request.app.state.analytics_service


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


def get_config(request: Request) -> Config:
    return request.app.state.config

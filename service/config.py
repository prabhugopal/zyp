"""Declarative env-driven config — one frozen dataclass; defaults live as field defaults, env
vars override."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    redis_url: str = "redis://localhost:6379/0"
    # 5000 collides with macOS's AirPlay Receiver (ControlCenter), which squats on it system-wide
    # and answers with a 403 before the app ever sees the request — 5055 avoids that entirely.
    base_url: str = "http://localhost:5055"
    rate_limit_per_minute: int = 30
    admin_username: str = "admin"
    # Fixed for local-dev convenience. Set ADMIN_PASSWORD for anything beyond local dev.
    admin_password: str = "zyp@123"
    auth_enabled: bool = True

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            redis_url=os.environ.get("REDIS_URL", cls.redis_url),
            base_url=os.environ.get("BASE_URL", cls.base_url),
            rate_limit_per_minute=int(os.environ.get("RATE_LIMIT_PER_MINUTE", cls.rate_limit_per_minute)),
            admin_username=os.environ.get("ADMIN_USERNAME", cls.admin_username),
            admin_password=os.environ.get("ADMIN_PASSWORD", cls.admin_password),
            auth_enabled=os.environ.get("AUTH_ENABLED", "true").lower() != "false",
        )

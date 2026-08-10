"""Shared Basic Auth dependency, used by the admin UI and by the analytics/export endpoint.
Split out of routes/admin.py so both can depend on it without importing one route module from
another."""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from config import Config
from deps import get_config

security = HTTPBasic(auto_error=False)


def require_auth(credentials: HTTPBasicCredentials | None = Depends(security),
                  config: Config = Depends(get_config)) -> None:
    if not config.auth_enabled:
        return
    valid = (credentials is not None
             and secrets.compare_digest(credentials.username, config.admin_username)
             and secrets.compare_digest(credentials.password, config.admin_password))
    if not valid:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": 'Basic realm="zyp"'})

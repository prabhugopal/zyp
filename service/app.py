"""FastAPI app factory. Services are constructed once here and stashed on app.state — routes pull
them from request.app.state via deps.py rather than importing module-level globals, so tests can
build a fresh app (and a fresh fakeredis/real-Redis client) per test with no shared state.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from config import Config
from errors import register_error_handlers
from rate_limit import RateLimiter
from redis_client import create_redis
from services.analytics_service import AnalyticsService
from services.link_service import LinkService

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("zyp")


def _announce(base_url: str) -> str:
    return (f"zyp is up - app: {base_url}  swagger: {base_url}/swagger-ui  "
            f"admin: {base_url}/admin  health: {base_url}/health")


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log.info(_announce(config.base_url))
        yield

    app = FastAPI(title="Zyp", version="v1", docs_url="/swagger-ui", lifespan=lifespan)

    redis_client = create_redis(config.redis_url)
    app.state.config = config
    app.state.link_service = LinkService(redis_client, config.base_url)
    app.state.analytics_service = AnalyticsService(redis_client)
    app.state.rate_limiter = RateLimiter(redis_client, config.rate_limit_per_minute)

    register_error_handlers(app)

    # Registered before redirect_router: FastAPI matches routes in registration order, and
    # redirect_router's GET /{code} is a single-segment catch-all that would otherwise shadow
    # both of these (a request for /health would be treated as a redirect lookup for code
    # "health" and 404 instead of reaching the handler below).
    @app.get("/", include_in_schema=False)
    def welcome() -> RedirectResponse:
        return RedirectResponse("/swagger-ui", status_code=302)

    @app.get("/health", tags=["Health"])
    def health() -> dict:
        return {"status": "ok"}

    from routes.admin import router as admin_router
    from routes.links import router as links_router
    from routes.redirect import router as redirect_router
    app.include_router(links_router)
    app.include_router(admin_router)
    app.include_router(redirect_router)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", port=5055)

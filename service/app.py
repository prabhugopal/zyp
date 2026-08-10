"""Flask app factory. Services are constructed once here and stashed on app.extensions["zyp"] —
routes pull them from current_app rather than importing module-level globals, so tests can build a
fresh app (and a fresh fakeredis client) per test with no shared state."""

from __future__ import annotations

import logging

from flask import Flask, redirect
from flask_smorest import Api

from config import Config
from errors import register_error_handlers
from rate_limit import RateLimiter
from redis_client import create_redis
from services.analytics_service import AnalyticsService
from services.link_service import LinkService


def create_app(config: Config | None = None) -> Flask:
    config = config or Config.from_env()
    app = Flask(__name__)

    app.config["API_TITLE"] = "Zyp"
    app.config["API_VERSION"] = "v1"
    app.config["OPENAPI_VERSION"] = "3.0.3"
    app.config["OPENAPI_URL_PREFIX"] = "/"
    app.config["OPENAPI_SWAGGER_UI_PATH"] = "/swagger-ui"
    app.config["OPENAPI_SWAGGER_UI_URL"] = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"

    redis_client = create_redis(config.redis_url)
    app.extensions["zyp"] = {
        "config": config,
        "link_service": LinkService(redis_client, config.base_url),
        "analytics_service": AnalyticsService(redis_client),
        "rate_limiter": RateLimiter(redis_client, config.rate_limit_per_minute),
    }

    register_error_handlers(app)

    api = Api(app)
    from routes.links import blp as links_blp
    from routes.redirect import blp as redirect_blp
    api.register_blueprint(links_blp)
    api.register_blueprint(redirect_blp)

    from routes.admin import admin_bp
    app.register_blueprint(admin_bp)

    @app.route("/")
    def welcome():
        return redirect("/swagger-ui")

    if not app.debug:
        logging.basicConfig(level=logging.INFO)

    return app


if __name__ == "__main__":
    create_app().run(port=5055)

"""RFC 7807 problem+json error responses for domain errors — mirrors sLink's error model.
flask-smorest's own marshmallow-validation errors (422) keep their default JSON shape rather than
being forced into problem+json too; chasing byte-for-byte parity with sLink's Spring
@RestControllerAdvice here would be effort spent on a corner nobody hits in the demo path.
"""

from __future__ import annotations

from flask import Flask, jsonify

from services.link_service import AliasTakenError, InvalidAliasError, LinkExpiredError, LinkNotFoundError

_TYPE_BASE = "https://zyp.dev/problems"


def _problem(status: int, title: str, detail: str, problem_type: str):
    response = jsonify({
        "type": f"{_TYPE_BASE}/{problem_type}",
        "title": title,
        "status": status,
        "detail": detail,
    })
    response.status_code = status
    response.content_type = "application/problem+json"
    return response


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(LinkNotFoundError)
    def _not_found(exc: LinkNotFoundError):
        return _problem(404, "Not Found", f"no link with code '{exc}'", "not-found")

    @app.errorhandler(LinkExpiredError)
    def _gone(exc: LinkExpiredError):
        return _problem(410, "Gone", f"link '{exc}' is expired or deactivated", "expired")

    @app.errorhandler(AliasTakenError)
    def _conflict(exc: AliasTakenError):
        return _problem(409, "Conflict", str(exc), "alias-taken")

    @app.errorhandler(InvalidAliasError)
    def _invalid_alias(exc: InvalidAliasError):
        return _problem(400, "Bad Request", str(exc), "invalid-alias")

    @app.errorhandler(ValueError)
    def _bad_request(exc: ValueError):
        return _problem(400, "Bad Request", str(exc), "validation-error")

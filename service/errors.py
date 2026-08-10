"""RFC 7807 problem+json error responses for domain errors. FastAPI's own request-validation
errors (422) keep their default JSON shape rather than being forced into problem+json too — a
deliberate scope cut for a corner nobody hits in the demo path.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from services.link_service import AliasTakenError, InvalidAliasError, LinkExpiredError, LinkNotFoundError

_TYPE_BASE = "https://zyp.dev/problems"


def _problem(status: int, title: str, detail: str, problem_type: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={"type": f"{_TYPE_BASE}/{problem_type}", "title": title, "status": status, "detail": detail},
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(LinkNotFoundError)
    async def _not_found(request: Request, exc: LinkNotFoundError) -> JSONResponse:
        return _problem(404, "Not Found", f"no link with code '{exc}'", "not-found")

    @app.exception_handler(LinkExpiredError)
    async def _gone(request: Request, exc: LinkExpiredError) -> JSONResponse:
        return _problem(410, "Gone", f"link '{exc}' is expired or deactivated", "expired")

    @app.exception_handler(AliasTakenError)
    async def _conflict(request: Request, exc: AliasTakenError) -> JSONResponse:
        return _problem(409, "Conflict", str(exc), "alias-taken")

    @app.exception_handler(InvalidAliasError)
    async def _invalid_alias(request: Request, exc: InvalidAliasError) -> JSONResponse:
        return _problem(400, "Bad Request", str(exc), "invalid-alias")

    @app.exception_handler(ValueError)
    async def _bad_request(request: Request, exc: ValueError) -> JSONResponse:
        return _problem(400, "Bad Request", str(exc), "validation-error")

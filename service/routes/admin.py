"""Minimal server-rendered view over the same service layer the JSON API uses — a human-friendly
complement to Swagger UI, not a replacement for the API. Basic Auth, toggleable via
config.auth_enabled for local-dev convenience."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from auth import require_auth
from config import Config
from deps import get_analytics_service, get_config, get_link_service
from services.analytics_service import AnalyticsService
from services.link_service import LinkService

router = APIRouter(prefix="/admin", tags=["Admin"])
_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "admin")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


@router.get("", name="admin_index", dependencies=[Depends(require_auth)])
def index(request: Request, link_service: LinkService = Depends(get_link_service),
          config: Config = Depends(get_config)):
    links, _total = link_service.list(page=0, size=20)
    return templates.TemplateResponse(request, "index.html", {"links": links, "base_url": config.base_url})


@router.post("/links", name="admin_create", dependencies=[Depends(require_auth)])
def create(originalUrl: str = Form(...), customAlias: str | None = Form(None),
           link_service: LinkService = Depends(get_link_service)):
    try:
        link = link_service.create(originalUrl, customAlias or None)
        return RedirectResponse(f"/admin?created={link.code}", status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/admin?error={exc}", status_code=303)


@router.get("/{code}", name="admin_detail", dependencies=[Depends(require_auth)])
def detail(code: str, request: Request, link_service: LinkService = Depends(get_link_service),
           analytics_service: AnalyticsService = Depends(get_analytics_service),
           config: Config = Depends(get_config)):
    try:
        link = link_service.get(code)
    except Exception:
        return RedirectResponse("/admin", status_code=303)
    analytics = analytics_service.get_analytics(code)
    return templates.TemplateResponse(request, "detail.html",
                                       {"link": link, "analytics": analytics, "base_url": config.base_url})

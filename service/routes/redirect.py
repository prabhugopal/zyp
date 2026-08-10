from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from deps import get_analytics_service, get_link_service
from services.analytics_service import AnalyticsService
from services.link_service import LinkService

router = APIRouter(tags=["Redirect"])


@router.get("/{code}", summary="Resolve a short link",
            description="302s to the original URL and records the click. 404 if the code is "
                         "unknown; 410 if it exists but is expired or deactivated.")
def redirect(code: str, request: Request,
             link_service: LinkService = Depends(get_link_service),
             analytics_service: AnalyticsService = Depends(get_analytics_service)) -> RedirectResponse:
    link = link_service.get_for_redirect(code)
    analytics_service.record_click(code, referrer=request.headers.get("referer", ""),
                                    user_agent=request.headers.get("user-agent", ""))
    return RedirectResponse(link.original_url, status_code=302)

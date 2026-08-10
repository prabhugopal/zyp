from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from auth import require_auth
from deps import get_analytics_service, get_link_service, get_rate_limiter
from rate_limit import RateLimiter
from schemas import (
    AnalyticsResponse,
    ClickRecordResponse,
    CreateLinkRequest,
    LinkPageResponse,
    LinkResponse,
    UpdateLinkRequest,
)
from services.analytics_service import AnalyticsService
from services.link_service import LinkService

router = APIRouter(prefix="/api/v1/links", tags=["Links"])

MAX_PAGE_SIZE = 100


def _link_response(link, link_service: LinkService) -> LinkResponse:
    return LinkResponse(code=link.code, originalUrl=link.original_url,
                         shortUrl=link_service.short_url(link.code), active=link.active,
                         createdAt=link.created_at, expiresAt=link.expires_at)


def _analytics_response(a) -> AnalyticsResponse:
    return AnalyticsResponse(
        totalClicks=a.total_clicks, clicksByDay=a.clicks_by_day,
        topReferrers=a.top_referrers, topUserAgents=a.top_user_agents,
        recentClicks=[ClickRecordResponse(clickedAt=c.clicked_at, referrer=c.referrer, userAgent=c.user_agent)
                      for c in a.recent_clicks],
    )


@router.post("", response_model=LinkResponse, status_code=201, summary="Create a short link",
             description="Shortens a URL. originalUrl must be http:// or https://. customAlias is "
                          "optional (auto-generated via Base62 if omitted) and, if given, must be "
                          "unused, 4-20 chars, and not a reserved word.")
def create_link(body: CreateLinkRequest, request: Request,
                 link_service: LinkService = Depends(get_link_service),
                 rate_limiter: RateLimiter = Depends(get_rate_limiter)) -> LinkResponse:
    client_id = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(client_id):
        raise HTTPException(429, "rate limit exceeded for link creation")
    link = link_service.create(body.originalUrl, body.customAlias, body.expiresAt)
    return _link_response(link, link_service)


@router.get("", response_model=LinkPageResponse, summary="List links",
            description="Paginated list of created links, newest first. size is capped at 100 "
                         "server-side regardless of what's requested.")
def list_links(page: int = 0, size: int = 20,
                link_service: LinkService = Depends(get_link_service)) -> LinkPageResponse:
    clamped_size = min(max(size, 1), MAX_PAGE_SIZE)
    links, total = link_service.list(page=page, size=clamped_size)
    return LinkPageResponse(links=[_link_response(l, link_service) for l in links],
                             page=page, size=clamped_size, totalElements=total)


@router.get("/{code}", response_model=LinkResponse, summary="Get link metadata",
            description="Returns the link's details without redirecting or recording a click.")
def get_link(code: str, link_service: LinkService = Depends(get_link_service)) -> LinkResponse:
    return _link_response(link_service.get(code), link_service)


@router.patch("/{code}", response_model=LinkResponse, summary="Update a link",
              description="Partial update: a null field is left unchanged. Use active=false to "
                           "deactivate without deleting.")
def update_link(code: str, body: UpdateLinkRequest,
                 link_service: LinkService = Depends(get_link_service)) -> LinkResponse:
    link = link_service.update(code, body.expiresAt, body.active)
    return _link_response(link, link_service)


@router.delete("/{code}", status_code=204, summary="Deactivate a link",
               description="Soft delete: marks the link inactive rather than removing it, so click "
                            "history is preserved.")
def delete_link(code: str, link_service: LinkService = Depends(get_link_service)) -> None:
    link_service.delete(code)


@router.get("/{code}/analytics", response_model=AnalyticsResponse, summary="Get link analytics",
            description="Aggregated click data: total clicks, clicks per day, top referrers, top "
                         "user agents, and the most recent clicks (newest first, capped at 50).")
def get_analytics(code: str, link_service: LinkService = Depends(get_link_service),
                   analytics_service: AnalyticsService = Depends(get_analytics_service)) -> AnalyticsResponse:
    link_service.get(code)  # 404s if unknown before returning analytics for a real code
    return _analytics_response(analytics_service.get_analytics(code))


@router.get("/{code}/analytics/export", summary="Export recent clicks as CSV",
            description="The same recent-clicks data as the analytics endpoint (newest first, "
                         "capped at 50), as a downloadable CSV file. Requires authentication: a "
                         "raw per-click export is treated as more sensitive than the aggregated "
                         "summary at GET .../analytics, which stays public.",
            dependencies=[Depends(require_auth)])
def export_analytics_csv(code: str, link_service: LinkService = Depends(get_link_service),
                          analytics_service: AnalyticsService = Depends(get_analytics_service)) -> Response:
    link_service.get(code)  # 404s if unknown
    csv_text = analytics_service.export_csv(code)
    return Response(csv_text, media_type="text/csv",
                     headers={"Content-Disposition": f'attachment; filename="{code}-clicks.csv"'})

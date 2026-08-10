from __future__ import annotations

from flask import Response, current_app, request
from flask.views import MethodView
from flask_smorest import Blueprint

from schemas import AnalyticsResponse, CreateLinkRequest, LinkPageResponse, LinkResponse, UpdateLinkRequest

blp = Blueprint("links", __name__, url_prefix="/api/v1/links",
                 description="Create, list, inspect, update, and delete short links.")

MAX_PAGE_SIZE = 100


def _link_dict(link) -> dict:
    return {
        "code": link.code,
        "originalUrl": link.original_url,
        "shortUrl": current_app.extensions["zyp"]["link_service"].short_url(link.code),
        "active": link.active,
        "createdAt": link.created_at,
        "expiresAt": link.expires_at,
    }


def _analytics_dict(a) -> dict:
    return {
        "totalClicks": a.total_clicks,
        "clicksByDay": a.clicks_by_day,
        "topReferrers": [list(t) for t in a.top_referrers],
        "topUserAgents": [list(t) for t in a.top_user_agents],
        "recentClicks": [{"clickedAt": c.clicked_at, "referrer": c.referrer, "userAgent": c.user_agent}
                          for c in a.recent_clicks],
    }


@blp.route("")
class LinksCollection(MethodView):
    @blp.arguments(CreateLinkRequest)
    @blp.response(201, LinkResponse)
    @blp.doc(summary="Create a short link",
             description="Shortens a URL. originalUrl must be http:// or https://. customAlias is "
                          "optional (auto-generated via Base62 if omitted) and, if given, must be "
                          "unused, 4-20 chars, and not a reserved word.")
    def post(self, link_data):
        rate_limiter = current_app.extensions["zyp"]["rate_limiter"]
        if not rate_limiter.allow(request.remote_addr or "unknown"):
            from flask import abort
            abort(429, "rate limit exceeded for link creation")
        link_service = current_app.extensions["zyp"]["link_service"]
        link = link_service.create(link_data["originalUrl"], link_data.get("customAlias"),
                                    link_data.get("expiresAt"))
        return _link_dict(link)

    @blp.response(200, LinkPageResponse)
    @blp.doc(summary="List links", description="Paginated list of created links, newest first.")
    def get(self):
        page = int(request.args.get("page", 0))
        size = min(max(int(request.args.get("size", 20)), 1), MAX_PAGE_SIZE)
        link_service = current_app.extensions["zyp"]["link_service"]
        links, total = link_service.list(page=page, size=size)
        return {"links": [_link_dict(l) for l in links], "page": page, "size": size, "totalElements": total}


@blp.route("/<string:code>")
class LinkItem(MethodView):
    @blp.response(200, LinkResponse)
    @blp.doc(summary="Get link metadata",
             description="Returns the link's details without redirecting or recording a click.")
    def get(self, code):
        link_service = current_app.extensions["zyp"]["link_service"]
        return _link_dict(link_service.get(code))

    @blp.arguments(UpdateLinkRequest)
    @blp.response(200, LinkResponse)
    @blp.doc(summary="Update a link",
             description="Partial update: a null field is left unchanged. Use active=false to "
                          "deactivate without deleting.")
    def patch(self, update_data, code):
        link_service = current_app.extensions["zyp"]["link_service"]
        link = link_service.update(code, update_data.get("expiresAt"), update_data.get("active"))
        return _link_dict(link)

    @blp.response(204)
    @blp.doc(summary="Deactivate a link",
             description="Soft delete: marks the link inactive rather than removing it, so click "
                          "history is preserved.")
    def delete(self, code):
        current_app.extensions["zyp"]["link_service"].delete(code)
        return ""


@blp.route("/<string:code>/analytics")
class LinkAnalyticsItem(MethodView):
    @blp.response(200, AnalyticsResponse)
    @blp.doc(summary="Get link analytics",
             description="Aggregated click data: total clicks, clicks per day, top referrers, top "
                          "user agents, and the most recent clicks (newest first, capped at 50).")
    def get(self, code):
        zyp = current_app.extensions["zyp"]
        zyp["link_service"].get(code)  # 404s if unknown before returning analytics for a real code
        return _analytics_dict(zyp["analytics_service"].get_analytics(code))


@blp.route("/<string:code>/analytics/export")
class LinkAnalyticsExport(MethodView):
    @blp.doc(summary="Export recent clicks as CSV",
             description="The same recent-clicks data as the analytics endpoint (newest first, "
                          "capped at 50), as a downloadable CSV file.")
    def get(self, code):
        zyp = current_app.extensions["zyp"]
        zyp["link_service"].get(code)  # 404s if unknown
        csv_text = zyp["analytics_service"].export_csv(code)
        return Response(csv_text, mimetype="text/csv",
                         headers={"Content-Disposition": f'attachment; filename="{code}-clicks.csv"'})

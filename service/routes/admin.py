"""Minimal server-rendered view over the same service layer the JSON API uses — a human-friendly
complement to Swagger UI, not a replacement for the API. Basic Auth, toggleable via
config.auth_enabled for local-dev convenience."""

from __future__ import annotations

from flask import Blueprint, current_app, redirect, render_template, request, url_for

admin_bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="../templates/admin")


def _authorized() -> bool:
    config = current_app.extensions["zyp"]["config"]
    if not config.auth_enabled:
        return True
    auth = request.authorization
    if not auth:
        return False
    return auth.username == config.admin_username and auth.password == config.admin_password


@admin_bp.before_request
def _require_auth():
    if not _authorized():
        from flask import Response
        return Response("Authentication required", 401, {"WWW-Authenticate": 'Basic realm="zyp-admin"'})


@admin_bp.route("")
def index():
    zyp = current_app.extensions["zyp"]
    links, _total = zyp["link_service"].list(page=0, size=20)
    return render_template("index.html", links=links, base_url=zyp["config"].base_url)


@admin_bp.route("/links", methods=["POST"])
def create():
    zyp = current_app.extensions["zyp"]
    try:
        link = zyp["link_service"].create(request.form["originalUrl"], request.form.get("customAlias") or None)
        return redirect(url_for("admin.index", created=link.code))
    except Exception as exc:  # surfaced as a flash-style query param, not a raw 500 to a form submit
        return redirect(url_for("admin.index", error=str(exc)))


@admin_bp.route("/<string:code>")
def detail(code):
    zyp = current_app.extensions["zyp"]
    try:
        link = zyp["link_service"].get(code)
    except Exception:
        return redirect(url_for("admin.index"))
    analytics = zyp["analytics_service"].get_analytics(code)
    return render_template("detail.html", link=link, analytics=analytics, base_url=zyp["config"].base_url)

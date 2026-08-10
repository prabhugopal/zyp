from __future__ import annotations

from flask import current_app, redirect, request
from flask.views import MethodView
from flask_smorest import Blueprint

blp = Blueprint("redirect", __name__, description="The actual short-link resolution endpoint.")


@blp.route("/<string:code>")
class Redirect(MethodView):
    @blp.doc(summary="Resolve a short link",
             description="302s to the original URL and records the click. 404 if the code is "
                          "unknown; 410 if it exists but is expired or deactivated.")
    def get(self, code):
        zyp = current_app.extensions["zyp"]
        link = zyp["link_service"].get_for_redirect(code)
        zyp["analytics_service"].record_click(code, referrer=request.referrer or "", user_agent=request.user_agent.string)
        return redirect(link.original_url, code=302)

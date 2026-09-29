"""CSRF guard for every session-authenticated botify_agent route.

Odoo checks CSRF only for ``type='http'`` routes; ``jsonrpc`` routes are
never checked (odoo/http.py, JsonRPCDispatcher). So each route calls
``check`` first: the web client's CSRF token in ``X-Botify-CSRF``, a
same-origin fetch, and a JSON body. No botify_agent route disables this.
"""

from .errors import OperationError


def check(request):
    headers = request.httprequest.headers
    site = headers.get("Sec-Fetch-Site")
    if site is not None and site != "same-origin":
        raise OperationError("CSRF_FAILED", "cross-site request refused")
    if not (headers.get("Content-Type") or "").startswith("application/json"):
        raise OperationError("CSRF_FAILED", "a JSON request is required")
    if not request.validate_csrf(headers.get("X-Botify-CSRF") or ""):
        raise OperationError("CSRF_FAILED", "missing or invalid CSRF token")

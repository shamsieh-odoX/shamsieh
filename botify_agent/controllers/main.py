"""Botify identity + end-user RPC controllers.

Design in one paragraph: the browser never says who the user is. ``/identity``
runs with ``auth="user"``, so Odoo has already authenticated the session and
``request.env.user`` is authoritative; we sign that. Botify verifies the
signature, then calls ``/rpc`` server-to-server with an HMAC and the uid it
verified. ``/rpc`` executes through ``with_user(uid)``, which yields a
``su=False`` environment, so Odoo — not Botify — decides what that user may read
or write.
"""

import json
import logging
import re
import time

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from ..models import botify_security

_logger = logging.getLogger(__name__)

# Methods Botify may invoke. An auth='none' endpoint that forwards arbitrary
# method names is remote code execution with extra steps, so the allowlist lives
# here as well as in Botify — the endpoint must be safe on its own terms.
READ_METHODS = {
    "read",
    "search",
    "search_read",
    "search_count",
    "read_group",
    "formatted_read_group",
    "fields_get",
    "name_search",
    "name_get",
    "get_portal_url",
    "default_get",
}

WRITE_METHODS = {"create", "write", "message_post", "activity_schedule"}

# Document lifecycle buttons. Mirrors SAFE_ACTION_METHODS in
# packages/api/src/services/odoo/odooTools.ts — keep the two in step.
ACTION_METHODS = {
    "action_confirm",
    "action_done",
    "action_cancel",
    "action_draft",
    "action_lock",
    "action_unlock",
    "button_confirm",
    "button_draft",
    "button_cancel",
    "action_post",
    "action_register_payment",
    "button_validate",
    "action_assign",
    "action_set_quantities_to_reservation",
    "action_set_won",
    "action_set_lost",
    "action_set_won_rainbowman",
    "toggle_active",
    "action_approve",
    "action_validate",
    "action_done_task",
    "action_create_payments",
}

ALLOWED_METHODS = READ_METHODS | WRITE_METHODS | ACTION_METHODS

# Never reachable regardless of the allowlist. `unlink` is absent from
# ALLOWED_METHODS already; naming it here documents that deletion is a decision,
# not an oversight.
FORBIDDEN_METHODS = {"unlink", "sudo", "with_user", "with_env", "browse", "_"}

MAX_LIMIT = 200

# Mirrors FORBIDDEN_WRITE_FIELD_RE / WORKFLOW_FIELD_RE in
# packages/api/src/services/odoo/odooTools.ts — keep the two in step.
#
# Botify already refuses these before a request is ever sent. This is the SAME
# check repeated at the one endpoint that actually performs the write, so it
# holds even if a Botify bug skips it, an older Botify build talks to a newer
# addon, or something else entirely calls this endpoint with a valid HMAC. An
# auth="none" endpoint has to be safe on its own terms, not on the caller's.
FORBIDDEN_WRITE_FIELD_RE = re.compile(
    r"password|secret|token|api_key|oauth|totp|signup|groups_id", re.IGNORECASE
)
# state/stage_id drive document workflow on nearly every business model; a
# bare write() skips the side effects the matching action_* method runs for
# that same transition (stock reservation, sequence numbers, validation).
# Force those through the ACTION_METHODS allowlist above instead of a raw
# field write.
WORKFLOW_FIELD_RE = re.compile(r"^(state|stage_id)$", re.IGNORECASE)


class ForbiddenFieldError(ValueError):
    """A write/create tried to touch a field this endpoint refuses outright."""


def _assert_write_fields_allowed(method, kwargs_in):
    """Field-level guard for write/create, independent of Odoo's own ACLs.

    Odoo's access rights/record rules answer "is this user allowed to touch
    this field on this record", which is necessary but not what this checks.
    This answers "should the ASSISTANT ever be allowed to set this field, for
    any user" — credentials and workflow-integrity fields are refused
    regardless of who is asking, exactly like the TypeScript side.
    """
    if method == "write":
        vals = kwargs_in.get("vals")
        if isinstance(vals, dict):
            for field in vals:
                if not isinstance(field, str):
                    continue
                if field.startswith("_") or FORBIDDEN_WRITE_FIELD_RE.search(field):
                    raise ForbiddenFieldError(
                        "Field %r cannot be modified through the assistant." % field
                    )
                if WORKFLOW_FIELD_RE.match(field):
                    raise ForbiddenFieldError(
                        "Field %r cannot be set directly — use the matching lifecycle "
                        "action method instead." % field
                    )
    elif method == "create":
        vals_list = kwargs_in.get("vals_list")
        for vals in vals_list if isinstance(vals_list, list) else []:
            if not isinstance(vals, dict):
                continue
            for field in vals:
                if not isinstance(field, str):
                    continue
                if field.startswith("_") or FORBIDDEN_WRITE_FIELD_RE.search(field):
                    raise ForbiddenFieldError(
                        "Field %r cannot be set through the assistant." % field
                    )


def _check_access(records, operation):
    """Explicit pre-flight permission check, across Odoo versions.

    Odoo 18 unified the two legacy calls into ``check_access``; 17 and earlier
    expose ``check_access_rights`` (model-level ACL) plus ``check_access_rule``
    (record rules). The ORM enforces both anyway on the actual call — this runs
    first so the failure happens before any query, and so the agent gets a clean
    AccessError instead of a partially-executed operation.
    """
    checker = getattr(records, "check_access", None)
    if callable(checker):
        checker(operation)
        return
    records.check_access_rights(operation)
    records.check_access_rule(operation)


def _user_all_groups(user):
    """A user's groups + implied groups, across Odoo versions.

    Odoo 19 split ``res.users.groups_id`` into ``group_ids`` (direct) and
    ``all_group_ids`` (direct + implied); 18 and earlier only have
    ``groups_id``, which already includes implied groups. Missing this broke
    every call to /botify_agent/identity on Odoo 19 with an AttributeError —
    verified live.
    """
    if "all_group_ids" in user._fields:
        return user.all_group_ids
    return user.groups_id


def _config(env):
    """Read addon settings.

    ``sudo()`` is deliberate and tightly scoped: ir.config_parameter is
    group_system-only, and this reads *the addon's own* configuration — not
    business data. It is the one privileged read in this file.
    """
    params = env["ir.config_parameter"].sudo()
    return {
        "enabled": params.get_param("botify_agent.enabled") in ("True", "true", "1", True),
        "base_url": (params.get_param("botify_agent.base_url") or "").strip(),
        "agent_id": (params.get_param("botify_agent.agent_id") or "").strip(),
        "installation_id": (params.get_param("botify_agent.installation_id") or "").strip(),
        "secret": (params.get_param("botify_agent.shared_secret") or "").strip(),
        "ttl": int(params.get_param("botify_agent.assertion_ttl") or 120),
        "allowed_group_id": params.get_param("botify_agent.allowed_group_id"),
    }


def _missing_config_fields(config):
    """Which of the three /rpc-blocking config fields are still empty, named.

    Pulled out of identity() so it is testable as plain data-in/data-out —
    no HTTP request or DB needed.
    """
    return [
        label
        for key, label in (
            ("secret", "Shared secret"),
            ("agent_id", "Botify agent ID"),
            ("installation_id", "Botify connection ID"),
        )
        if not config[key]
    ]


def _json_response(payload, status=200):
    return request.make_response(
        json.dumps(payload),
        headers=[("Content-Type", "application/json; charset=utf-8")],
        status=status,
    )


def _error(message, status=400, name=None):
    body = {"error": {"message": message}}
    if name:
        body["error"]["name"] = name
    return _json_response(body, status=status)


class BotifyIdentityController(http.Controller):
    """Mints identity assertions for the logged-in Odoo user."""

    @http.route(
        "/botify_agent/identity",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def identity(self, **kwargs):
        """Return a short-lived assertion naming the CURRENT user.

        Every claim is read from ``request.env.user`` on the server. There is no
        parameter by which a caller can ask for a different subject — that
        absence is the impersonation defence, so resist adding one.
        """
        config = _config(request.env)
        if not config["enabled"]:
            return {"error": "Botify agent is disabled on this database."}
        missing = _missing_config_fields(config)
        if missing:
            # Naming exactly which field(s) are still empty turns this from a
            # "why doesn't it work" support thread into a one-look fix — all
            # three live on the same Settings > Botify Agent screen.
            return {
                "error": "Botify agent is not fully configured. Missing: %s."
                % ", ".join(missing)
            }

        user = request.env.user

        # Portal/public users share a partner-level view of the system and are
        # not employees; keep them out unless someone deliberately opts in.
        if user.share:
            return {"error": "Portal users cannot use the Botify agent."}
        if user.id == 1:
            # OdooBot/superuser would bypass every record rule downstream.
            return {"error": "The superuser cannot use the Botify agent."}

        group_id = config["allowed_group_id"]
        if group_id:
            # _user_all_groups() already contains implied groups, so a plain
            # membership test covers inheritance without resolving xml ids
            # (groups created in the UI generally have none).
            try:
                allowed = int(group_id) in _user_all_groups(user).ids
            except (TypeError, ValueError):
                allowed = False
            if not allowed:
                return {"error": "You are not allowed to use the Botify agent."}

        now = int(time.time())
        allowed_company_ids = request.env.companies.ids or user.company_ids.ids

        payload = {
            "iss": "odoo:%s" % request.env.cr.dbname,
            "sub": str(user.id),
            "aud": config["agent_id"],
            "bi": config["installation_id"],
            "jti": botify_security.new_nonce(),
            "iat": now,
            "exp": now + config["ttl"],
            "name": user.name or "",
            "login": user.login or "",
            "email": user.email or "",
            "company_id": user.company_id.id,
            "allowed_company_ids": allowed_company_ids,
            "share": user.share,
            # Audit/personalisation only. Botify explicitly does not use these
            # for authorization — permissions are re-evaluated here on every
            # call, so a stale group list cannot widen anything.
            "groups": _user_all_groups(user).mapped("full_name")[:64],
        }

        _logger.info(
            "botify_agent: issued identity assertion for uid=%s (%s)", user.id, user.login
        )
        return {
            "assertion": botify_security.sign_jwt(payload, config["secret"]),
            "expires_in": config["ttl"],
            "base_url": config["base_url"],
            "agent_id": config["agent_id"],
            "platform": "odoo",
            "user": {"id": user.id, "name": user.name},
        }


class BotifyRpcController(http.Controller):
    """Executes Botify's ORM calls as a named end user."""

    @http.route(
        "/botify_agent/rpc",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def rpc(self, **kwargs):
        """Run one ORM call as ``uid``, under that user's own permissions.

        ``auth="none"`` because the caller is Botify's server, which holds no
        Odoo session — the HMAC is the credential. ``type="http"`` because the
        signature covers the raw body, which Odoo's json dispatcher would have
        already consumed and re-serialised.
        """
        raw_body = request.httprequest.get_data()
        headers = request.httprequest.headers

        config = _config(request.env)
        if not config["enabled"] or not config["secret"]:
            return _error("Botify agent is not enabled here.", status=503)

        try:
            botify_security.verify_request(
                config["secret"],
                headers.get("X-Botify-Timestamp", ""),
                raw_body,
                headers.get("X-Botify-Signature", ""),
            )
        except ValueError as exc:
            _logger.warning("botify_agent: rejected RPC (%s)", exc)
            # Uniform message: distinguishing "bad signature" from "stale" helps
            # an attacker tune their attempt.
            return _error("Request rejected.", status=401)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return _error("Malformed JSON body.", status=400)

        # The signature proves the payload came from Botify; it does not make the
        # payload sane. Validate every field before it reaches the ORM.
        if payload.get("installation_id") != config["installation_id"]:
            return _error("Unknown installation.", status=401)

        model_name = payload.get("model")
        method = payload.get("method")
        if not isinstance(model_name, str) or not isinstance(method, str):
            return _error("model and method are required.", status=400)
        if method.startswith("_") or method in FORBIDDEN_METHODS:
            return _error("Method %r is not permitted." % method, status=403)
        if method not in ALLOWED_METHODS:
            return _error("Method %r is not permitted." % method, status=403)

        try:
            uid = int(payload.get("uid"))
        except (TypeError, ValueError):
            return _error("A numeric uid is required.", status=400)
        if uid <= 1:
            # uid 1 is the superuser: with_user(1) returns a superuser
            # environment by Odoo's own convention, which would silently bypass
            # every record rule. Refuse outright.
            return _error("Refusing to act as the superuser.", status=403)

        env = request.env
        user = env["res.users"].sudo().browse(uid).exists()
        if not user:
            return _error("Unknown user.", status=403)
        if not user.active:
            # Deactivated employee: sessions in Botify may still look live.
            return _error("This Odoo user is no longer active.", status=403)
        if user.share:
            return _error("Portal users cannot be acted for.", status=403)

        allowed_company_ids = payload.get("allowed_company_ids") or []
        if not isinstance(allowed_company_ids, list):
            allowed_company_ids = []
        allowed_company_ids = [
            int(cid) for cid in allowed_company_ids if isinstance(cid, (int, str)) and str(cid).isdigit()
        ]
        # Fall back to the user's own companies. Odoo re-validates whatever we
        # pass (Environment.companies raises AccessError for anything outside
        # the user's set when su=False), so this cannot widen access — it only
        # narrows or matches.
        if not allowed_company_ids:
            allowed_company_ids = user.company_ids.ids

        ids = payload.get("ids") or []
        if not isinstance(ids, list):
            ids = []
        ids = [int(i) for i in ids if isinstance(i, (int, str)) and str(i).isdigit()]

        kwargs_in = payload.get("kwargs") or {}
        if not isinstance(kwargs_in, dict):
            return _error("kwargs must be an object.", status=400)
        # Context is ours to set: letting the caller inject one would let it slip
        # in active_test=False, or a company context we just validated away.
        kwargs_in.pop("context", None)
        if "limit" in kwargs_in:
            try:
                kwargs_in["limit"] = min(int(kwargs_in["limit"]), MAX_LIMIT)
            except (TypeError, ValueError):
                kwargs_in.pop("limit")

        try:
            # THE line this whole addon exists for. with_user() returns an
            # environment with su=False (odoo/models.py), so access rights,
            # record rules and company scoping are applied to `user` exactly as
            # if they had run the query from the web client.
            target = (
                env[model_name]
                .with_user(user)
                .with_context(allowed_company_ids=allowed_company_ids)
            )
        except KeyError:
            return _error("Unknown model %r." % model_name, status=404)

        try:
            _assert_write_fields_allowed(method, kwargs_in)
        except ForbiddenFieldError as exc:
            return _error(str(exc), status=403)

        try:
            if ids:
                records = target.browse(ids)
                # Fails here, before any data is read, if a record rule hides
                # one of them — unauthorised rows never reach the model.
                _check_access(records, "read" if method in READ_METHODS else "write")
                result = getattr(records, method)(**kwargs_in)
            else:
                result = getattr(target, method)(**kwargs_in)
        except AccessError as exc:
            _logger.info("botify_agent: access denied for uid=%s on %s.%s", uid, model_name, method)
            return _json_response(
                {"error": {"name": "odoo.exceptions.AccessError", "message": str(exc)}}
            )
        except (UserError, ValidationError) as exc:
            return _json_response(
                {"error": {"name": type(exc).__name__, "message": str(exc)}}
            )
        except AttributeError:
            return _error("Model %r has no method %r." % (model_name, method), status=404)
        except Exception as exc:  # pragma: no cover - defensive
            _logger.exception("botify_agent: RPC failed")
            return _json_response(
                {"error": {"name": "InternalError", "message": str(exc)}}, status=500
            )

        _logger.info(
            "botify_agent: uid=%s ran %s.%s (session=%s)",
            uid,
            model_name,
            method,
            payload.get("session_id"),
        )
        return _json_response({"result": _jsonify(result)})


def _jsonify(value):
    """Make ORM return values JSON-safe (recordsets, dates, bytes)."""
    from datetime import date, datetime

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, dict):
        return {str(k): _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    if hasattr(value, "ids"):
        return value.ids
    return str(value)

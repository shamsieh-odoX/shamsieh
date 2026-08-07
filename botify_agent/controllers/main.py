"""Botify identity + end-user RPC controllers.

Design in one paragraph: the browser never says who the user is. ``/identity``
runs with ``auth="user"``, so Odoo has already authenticated the session and
``request.env.user`` is authoritative; we sign that AND mint a per-user
delegation credential (``botify.agent.delegation``). Botify verifies the
identity assertion, then exchanges the delegation (proof-of-possession, never
transmitting the raw key) for a short-lived, single-use, Odoo-signed grant via
``/botify_agent/grant`` (``controllers/grant.py``) naming exactly one uid and
one operation. ``/rpc`` executes through ``with_user(uid)`` — which yields a
``su=False`` environment, so Odoo, not Botify, decides what that user may read
or write — but ONLY after verifying the grant's signature, recomputing its
operation hash from the actual request body, and atomically consuming its
``jti`` so it can never be replayed. See docs/odoo/architecture.md.
"""

import datetime
import json
import logging
import time

from odoo import fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from . import _shared
from ..models import botify_canonical, botify_policy, botify_security

_logger = logging.getLogger(__name__)

# Kept for the /rpc allowlist gate (defence in depth alongside the policy
# manifest's own method map — a method absent from BOTH is refused).
FORBIDDEN_METHODS = {"unlink", "sudo", "with_user", "with_env", "browse", "_"}

DELEGATION_TTL_SECONDS = 900  # 15 minutes \u2014 independent of, and shorter than, the identity session's own TTL.


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


class BotifyIdentityController(http.Controller):
    """Mints identity assertions + a per-user delegation credential for the
    logged-in Odoo user."""

    @http.route(
        "/botify_agent/identity",
        type="json",
        auth="user",
        methods=["POST"],
        csrf=False,
        # Mints + persists a delegation credential (a write) on every call.
        # See the matching comment on /botify_agent/grant — Odoo 17+ defaults
        # HTTP routes to a read-only cursor; this route needs a writable one
        # from the start.
        readonly=False,
    )
    def identity(self, **kwargs):
        """Return a short-lived assertion naming the CURRENT user, plus a
        delegation credential Botify will later present (via proof of
        possession, never the raw key itself) to request per-operation
        grants. Every claim is read from ``request.env.user`` on the server
        \u2014 there is no parameter by which a caller can ask for a different
        subject. That absence is the impersonation defence; resist adding one.
        """
        cfg = _shared.config(request.env)
        if not cfg["enabled"]:
            return {"error": "Botify agent is disabled on this database."}
        missing = _shared.missing_config_fields(cfg)
        if missing:
            return {
                "error": "Botify agent is not fully configured. Missing: %s."
                % ", ".join(missing)
            }

        user = request.env.user

        if user.share:
            return {"error": "Portal users cannot use the Botify agent."}
        if user.id == 1:
            return {"error": "The superuser cannot use the Botify agent."}

        group_id = cfg["allowed_group_id"]
        if group_id:
            try:
                allowed = int(group_id) in _shared.user_all_groups(user).ids
            except (TypeError, ValueError):
                allowed = False
            if not allowed:
                return {"error": "You are not allowed to use the Botify agent."}

        now = int(time.time())
        allowed_company_ids = request.env.companies.ids or user.company_ids.ids

        payload = {
            "iss": "odoo:%s" % request.env.cr.dbname,
            "sub": str(user.id),
            "aud": cfg["agent_id"],
            "bi": cfg["installation_id"],
            "jti": botify_security.new_nonce(),
            "iat": now,
            "exp": now + cfg["ttl"],
            "name": user.name or "",
            "login": user.login or "",
            "email": user.email or "",
            "company_id": user.company_id.id,
            "allowed_company_ids": allowed_company_ids,
            "share": user.share,
            # This user's Odoo timezone, so the assistant can resolve "today"
            # and "in three days" against the clock the user actually works in
            # rather than UTC. Personalisation only — never an authorization
            # input. Falls back to UTC Botify-side when unset.
            "tz": user.tz or "",
            # Audit/personalisation only \u2014 Botify does not use these for
            # authorization; permissions are re-evaluated on every grant.
            "groups": _shared.user_all_groups(user).mapped("full_name")[:64],
        }

        delegation_secret = botify_security.new_secret()
        delegation = request.env["botify.agent.delegation"].sudo().create({
            "uid": user.id,
            "installation_id": cfg["installation_id"],
            "agent_id": cfg["agent_id"],
            "secret_key": delegation_secret,
            "allowed_company_ids": json.dumps(allowed_company_ids),
            "expires_at": fields.Datetime.now() + datetime.timedelta(seconds=DELEGATION_TTL_SECONDS),
        })

        _logger.info(
            "botify_agent: issued identity assertion + delegation=%s for uid=%s (%s)",
            delegation.id, user.id, user.login,
        )
        return {
            "assertion": botify_security.sign_jwt(payload, cfg["secret"]),
            "expires_in": cfg["ttl"],
            "base_url": cfg["base_url"],
            "agent_id": cfg["agent_id"],
            "platform": "odoo",
            "user": {"id": user.id, "name": user.name},
            "delegation_id": str(delegation.id),
            "delegation_key": delegation_secret,
            "delegation_expires_in": DELEGATION_TTL_SECONDS,
        }


class BotifyRpcController(http.Controller):
    """Executes one grant-authorized ORM call as its named end user."""

    @http.route(
        "/botify_agent/rpc",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
        # Consumes a single-use nonce and bumps delegation.last_used_at before
        # ever reaching the caller's own ORM call — both writes. See the
        # matching comment on /botify_agent/grant: without readonly=False,
        # Odoo's read-only-by-default HTTP cursor makes the nonce INSERT
        # intermittently raise ReadOnlySqlTransaction, which the deliberately
        # broad except in the nonce-consumption block below then reports as
        # `grant_replayed` — a false replay rejection of a perfectly valid,
        # first-use grant. Verified live against a real Odoo 18 instance.
        readonly=False,
    )
    def rpc(self, **kwargs):
        """Run one ORM call as the grant's ``sub`` (uid), under that user's own
        permissions. ``auth="none"`` because the caller is Botify's server,
        which holds no Odoo session \u2014 the transport HMAC is the transport
        credential; the grant (``X-Botify-Grant``) is the AUTHORIZATION
        credential, and is what names the acting uid \u2014 the body's own `uid`
        field, if present, is never trusted (see threat-model.md \u00a73.1).
        """
        raw_body = request.httprequest.get_data()
        headers = request.httprequest.headers
        env = request.env

        cfg = _shared.config(env)
        if not cfg["enabled"] or not cfg["secret"]:
            return _shared.error("Botify agent is not enabled here.", status=503)

        try:
            _shared.verify_transport(cfg, headers, raw_body)
        except ValueError as exc:
            _logger.warning("botify_agent: rejected RPC (transport: %s)", exc)
            return _shared.error("Request rejected.", status=401, name="transport_invalid")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return _shared.error("Malformed JSON body.", status=400)

        if payload.get("installation_id") != cfg["installation_id"]:
            return _shared.error("Unknown installation.", status=401, name="installation_mismatch")

        grant_token = headers.get("X-Botify-Grant", "")
        if not grant_token:
            return _shared.error("Missing grant.", status=401, name="grant_missing")
        try:
            claims = botify_security.verify_grant(grant_token, cfg["grant_signing_key"])
        except ValueError as exc:
            reason = "grant_expired" if "expired" in str(exc) else "grant_signature_invalid"
            _logger.warning("botify_agent: rejected RPC (grant: %s)", exc)
            return _shared.error("Grant rejected.", status=401, name=reason)

        if claims.get("bi") != cfg["installation_id"]:
            return _shared.error("Grant is for a different installation.", status=401, name="installation_mismatch")
        if claims.get("aud") != cfg["agent_id"]:
            return _shared.error("Grant is for a different agent.", status=401, name="audience_mismatch")
        if claims.get("iss") != "odoo:%s" % env.cr.dbname:
            return _shared.error("Grant issuer does not match this database.", status=401, name="audience_mismatch")

        model_name = payload.get("model")
        method = payload.get("method")
        if not isinstance(model_name, str) or not isinstance(method, str):
            return _shared.error("model and method are required.", status=400)
        if method.startswith("_") or method in FORBIDDEN_METHODS:
            return _shared.error("Method %r is not permitted." % method, status=403, name="method_forbidden")

        ids = _shared.sanitize_ids(payload.get("ids") or [])
        domain = payload.get("domain")
        kwargs_in = payload.get("kwargs") if isinstance(payload.get("kwargs"), dict) else {}
        kwargs_in = dict(kwargs_in)
        # Context is ours to set: letting the caller inject one would let it
        # slip in active_test=False, or a company context we validate below.
        kwargs_in.pop("context", None)
        limits = botify_policy.get_policy_manifest()["limits"]
        if "limit" in kwargs_in:
            try:
                kwargs_in["limit"] = min(int(kwargs_in["limit"]), limits["maxRpcLimit"])
            except (TypeError, ValueError):
                kwargs_in.pop("limit")

        # The `oph` claim binds the grant to THIS exact operation. Recomputing
        # it from the body actually received \u2014 not from what the client
        # claims it sent \u2014 is what makes a captured grant useless against a
        # different model/method/ids/domain/kwargs.
        actual_oph = botify_canonical.operation_hash(model_name, method, ids=ids, domain=domain, kwargs=kwargs_in)
        if actual_oph != claims.get("oph"):
            _logger.warning(
                "botify_agent: grant/operation mismatch uid=%s %s.%s", claims.get("sub"), model_name, method
            )
            return _shared.error("Grant does not match this operation.", status=403, name="grant_operation_mismatch")

        # Atomically consume the jti. ANY failure to insert (unique violation
        # or otherwise) is treated as replay and the call is refused \u2014
        # fail-closed rather than risk a second execution of an
        # already-consumed grant (see docs/odoo/threat-model.md \u00a73.2).
        jti = claims.get("jti")
        if not jti:
            return _shared.error("Grant is missing a jti.", status=401, name="grant_replayed")
        try:
            with env.cr.savepoint():
                env["botify.agent.nonce"].sudo().create({
                    "jti": jti,
                    "uid": claims.get("sub"),
                    "model": model_name,
                    "method": method,
                })
        except Exception as exc:  # noqa: BLE001 \u2014 deliberately broad, see docstring above.
            _logger.info("botify_agent: grant replay rejected jti=%s (%s)", jti, exc)
            return _shared.error("This grant has already been used.", status=409, name="grant_replayed")

        try:
            uid = int(claims["sub"])
        except (TypeError, ValueError, KeyError):
            return _shared.error("Grant has no valid subject.", status=401, name="grant_signature_invalid")
        if uid <= 1:
            return _shared.error("Refusing to act as the superuser.", status=403, name="superuser_forbidden")

        user = env["res.users"].sudo().browse(uid).exists()
        if not user:
            return _shared.error("Unknown user.", status=403, name="inactive_user")
        if not user.active:
            return _shared.error("This Odoo user is no longer active.", status=403, name="inactive_user")
        if user.share:
            return _shared.error("Portal users cannot be acted for.", status=403, name="portal_user")

        allowed_company_ids = _shared.sanitize_company_ids(claims.get("cids") or [])
        if not allowed_company_ids:
            allowed_company_ids = user.company_ids.ids
        elif not set(allowed_company_ids).issubset(set(user.company_ids.ids)):
            # Defence in depth: the grant's cids were validated against the
            # user's companies at issuance, but a permission change between
            # grant and use (AC: "permission changes") must not widen access.
            return _shared.error("Company scope no longer valid for this user.", status=403,
                                  name="company_out_of_scope")

        fields_touched = _shared.extract_write_fields(method, kwargs_in)
        granted_scopes = set(claims.get("scopes") or [])
        # Custom-model classification this grant was issued under. It comes out
        # of the Odoo-SIGNED grant whose signature was verified above, not from
        # the request body, so /rpc reaches the same decision as /grant without
        # re-trusting the caller. Re-sanitized anyway (defence in depth) and
        # re-gated on the Odoo-side master switch, so turning that switch off
        # invalidates in-flight grants rather than letting them drain.
        tenant_model = None
        if cfg["allow_custom_models"]:
            tenant_model = botify_policy.sanitize_tenant_model(claims.get("tmc"), model_name)
        try:
            decision = botify_policy.evaluate(
                model_name,
                method,
                fields=fields_touched,
                ids=ids,
                granted_op_classes=granted_scopes,
                tenant_model=tenant_model,
            )
        except botify_policy.PolicyDenied as exc:
            _logger.info("botify_agent: policy denied uid=%s %s.%s (%s)", uid, model_name, method, exc.reason)
            return _shared.error(exc.message, status=403, name=exc.reason)

        try:
            target = env[model_name].with_user(user).with_context(allowed_company_ids=allowed_company_ids)
        except KeyError:
            return _shared.error("Unknown model %r." % model_name, status=404)

        try:
            if ids:
                records = target.browse(ids)
                _shared.check_access(records, "read" if decision["opClass"] == "read" else "write")
                result = getattr(records, method)(**kwargs_in)
            else:
                result = getattr(target, method)(**kwargs_in)
        except AccessError as exc:
            _logger.info("botify_agent: access denied for uid=%s on %s.%s", uid, model_name, method)
            return _shared.json_response(
                {"error": {"name": "odoo.exceptions.AccessError", "message": str(exc)}}
            )
        except (UserError, ValidationError) as exc:
            return _shared.json_response(
                {"error": {"name": type(exc).__name__, "message": str(exc)}}
            )
        except AttributeError:
            return _shared.error("Model %r has no method %r." % (model_name, method), status=404)
        except Exception as exc:  # pragma: no cover - defensive
            _logger.exception("botify_agent: RPC failed")
            return _shared.json_response(
                {"error": {"name": "InternalError", "message": str(exc)}}, status=500
            )

        _logger.info(
            "botify_agent: uid=%s ran %s.%s op_class=%s jti=%s",
            uid, model_name, method, decision["opClass"], jti,
        )
        return _shared.json_response({"result": _jsonify(result), "op_class": decision["opClass"]})

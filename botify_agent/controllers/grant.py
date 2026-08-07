"""Mints short-lived, single-use, Odoo-signed per-operation grants.

This is the credential layer that replaces "the shared secret alone can name
any uid" (docs/odoo/threat-model.md ยง3.1). A grant names exactly one uid, one
operation (via `oph`), one company scope and one op class, expires in
seconds, and can only ever be consumed once (`/botify_agent/rpc` atomically
inserts its `jti` before executing). See docs/odoo/architecture.md ยง2.2.
"""

import json
import logging
import time

from odoo import fields, http
from odoo.http import request

from . import _shared
from ..models import botify_canonical, botify_policy, botify_security

_logger = logging.getLogger(__name__)

# Six op classes an attachment can independently grant (docs/odoo/policy.md).
VALID_OP_CLASSES = {
    "read",
    "capture_write",
    "normal_write",
    "financial_write",
    "lifecycle_action",
    "batch_action",
}


class BotifyGrantController(http.Controller):
    @http.route(
        "/botify_agent/grant",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
        # This route WRITES (issues/validates the delegation, bumps
        # last_used_at). Odoo 17+ defaults HTTP routes to a read-only cursor
        # (for read-replica routing); leaving that default here means the
        # first write on the route intermittently raises
        # ReadOnlySqlTransaction, which the nonce/delegation write paths must
        # then treat as an ambiguous failure. Declaring readonly=False makes
        # this route write-capable from the start, matching what it actually
        # does — verified against a real Odoo 18 instance (see
        # docs/odoo/final-report.md).
        readonly=False,
    )
    def grant(self, **kwargs):
        raw_body = request.httprequest.get_data()
        headers = request.httprequest.headers
        env = request.env

        cfg = _shared.config(env)
        if not cfg["enabled"] or not cfg["secret"]:
            return _shared.error("Botify agent is not enabled here.", status=503)

        try:
            _shared.verify_transport(cfg, headers, raw_body)
        except ValueError as exc:
            _logger.warning("botify_agent: rejected grant request (transport: %s)", exc)
            return _shared.error("Request rejected.", status=401, name="transport_invalid")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return _shared.error("Malformed JSON body.", status=400)

        if payload.get("installation_id") != cfg["installation_id"]:
            return _shared.error("Unknown installation.", status=401, name="installation_mismatch")

        delegation_id = payload.get("delegation_id")
        try:
            delegation = env["botify.agent.delegation"].sudo().browse(int(delegation_id)).exists()
        except (TypeError, ValueError):
            delegation = None
        if not delegation:
            return _shared.error("Unknown delegation.", status=403, name="delegation_unknown")
        if delegation.installation_id != cfg["installation_id"]:
            return _shared.error("Delegation belongs to a different installation.", status=403,
                                  name="installation_mismatch")
        if delegation.revoked_at:
            return _shared.error("Delegation has been revoked.", status=403, name="delegation_revoked")
        if not delegation.is_live():
            return _shared.error("Delegation has expired.", status=403, name="delegation_expired")

        proof = headers.get("X-Botify-Delegation-Proof", "")
        ts = headers.get("X-Botify-Timestamp", "")
        try:
            botify_security.verify_delegation_proof(delegation.secret_key, ts, raw_body, proof)
        except ValueError as exc:
            _logger.warning("botify_agent: rejected grant request (delegation proof: %s)", exc)
            return _shared.error("Delegation proof rejected.", status=401, name="delegation_proof_invalid")

        uid = delegation.uid
        user = env["res.users"].sudo().browse(uid).exists()
        if not user:
            return _shared.error("Unknown user.", status=403, name="inactive_user")
        if not user.active:
            return _shared.error("This Odoo user is no longer active.", status=403, name="inactive_user")
        if user.share:
            return _shared.error("Portal users cannot be acted for.", status=403, name="portal_user")
        if user.id == 1:
            return _shared.error("Refusing to act as the superuser.", status=403, name="superuser_forbidden")

        try:
            delegation_allowed_cids = set(json.loads(delegation.allowed_company_ids or "[]"))
        except ValueError:
            delegation_allowed_cids = set()
        requested_cids = set(_shared.sanitize_company_ids(payload.get("allowed_company_ids") or []))
        base_cids = set(user.company_ids.ids)
        if not requested_cids:
            requested_cids = delegation_allowed_cids or base_cids
        # Escalation guard: a grant can never cover a company outside both the
        # user's own companies AND (when the delegation narrowed it further)
        # the delegation's own allowed set.
        allowed_ceiling = base_cids if not delegation_allowed_cids else (base_cids & delegation_allowed_cids)
        if not requested_cids.issubset(allowed_ceiling):
            return _shared.error("Requested company scope exceeds what is allowed.", status=403,
                                  name="company_out_of_scope")

        try:
            delegation_scopes = set(json.loads(delegation.scopes or "[]"))
        except ValueError:
            delegation_scopes = set()

        model_name = payload.get("model")
        method = payload.get("method")
        if not isinstance(model_name, str) or not isinstance(method, str):
            return _shared.error("model and method are required.", status=400)

        ids = _shared.sanitize_ids(payload.get("ids") or [])
        domain = payload.get("domain")
        kwargs_in = payload.get("kwargs") if isinstance(payload.get("kwargs"), dict) else {}
        fields_touched = _shared.extract_write_fields(method, kwargs_in)

        op_class_override = None
        if payload.get("is_batch") is True and len(ids) > 1:
            op_class_override = "batch_action"

        try:
            decision = botify_policy.evaluate(
                model_name,
                method,
                fields=fields_touched,
                ids=ids,
                batch_size=len(ids) if op_class_override else None,
                op_class_override=op_class_override,
                granted_op_classes=delegation_scopes & VALID_OP_CLASSES,
            )
        except botify_policy.PolicyDenied as exc:
            _logger.info("botify_agent: grant denied uid=%s %s.%s (%s)", uid, model_name, method, exc.reason)
            return _shared.error(exc.message, status=403, name=exc.reason)

        op_class = decision["opClass"]

        now = int(time.time())
        oph = botify_canonical.operation_hash(model_name, method, ids=ids, domain=domain, kwargs=kwargs_in)
        claims = {
            "iss": "odoo:%s" % env.cr.dbname,
            "bi": cfg["installation_id"],
            "aud": cfg["agent_id"],
            "sub": uid,
            "cids": sorted(requested_cids),
            "scopes": [op_class],
            "oph": oph,
            "jti": botify_security.new_nonce(),
            "iat": now,
            "exp": now + cfg["grant_ttl"],
        }
        token = botify_security.sign_grant(claims, cfg["grant_signing_key"])
        delegation.sudo().write({"last_used_at": fields.Datetime.now()})
        return _shared.json_response(
            {
                "grant": token,
                "expires_in": cfg["grant_ttl"],
                "op_class": op_class,
                "risk_level": decision["riskLevel"],
            }
        )

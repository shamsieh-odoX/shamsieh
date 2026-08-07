"""Helpers shared by the identity, grant and rpc controllers.

Split out of main.py during the odoo-enterprise-rebuild so grant.py does not
have to import from main.py (which would create a controller-to-controller
import — Odoo controllers are meant to be independent HTTP surfaces).
"""

import json
import logging

from odoo.http import request

from ..models import botify_security

_logger = logging.getLogger(__name__)

DEFAULT_GRANT_TTL = 90
MIN_GRANT_TTL = 15
MAX_GRANT_TTL = 300
DEFAULT_SECRET_GRACE_HOURS = 24


def config(env):
    """Read addon settings. sudo() is deliberate and tightly scoped: this
    reads *the addon's own* configuration, not business data."""
    params = env["ir.config_parameter"].sudo()

    def _int(key, default):
        try:
            return int(params.get_param(key) or default)
        except (TypeError, ValueError):
            return default

    grant_key = (params.get_param("botify_agent.grant_signing_key") or "").strip()
    if not grant_key:
        # Auto-generated on first use, once. Never transmitted by any route —
        # this key only ever signs grants and verifies them, both server-side.
        grant_key = botify_security.new_secret()
        params.set_param("botify_agent.grant_signing_key", grant_key)

    return {
        "enabled": params.get_param("botify_agent.enabled") in ("True", "true", "1", True),
        "base_url": (params.get_param("botify_agent.base_url") or "").strip(),
        "agent_id": (params.get_param("botify_agent.agent_id") or "").strip(),
        "installation_id": (params.get_param("botify_agent.installation_id") or "").strip(),
        "secret": (params.get_param("botify_agent.shared_secret") or "").strip(),
        "secret_previous": (params.get_param("botify_agent.shared_secret_previous") or "").strip(),
        "secret_rotated_at": (params.get_param("botify_agent.secret_rotated_at") or "").strip(),
        "secret_grace_hours": _int("botify_agent.secret_grace_hours", DEFAULT_SECRET_GRACE_HOURS),
        "ttl": _int("botify_agent.assertion_ttl", 120),
        "grant_ttl": max(MIN_GRANT_TTL, min(MAX_GRANT_TTL, _int("botify_agent.grant_ttl", DEFAULT_GRANT_TTL))),
        "allowed_group_id": params.get_param("botify_agent.allowed_group_id"),
        "grant_signing_key": grant_key,
        # Odoo-side half of the custom-model decision. Default False, and
        # settable only from inside this database — so a compromised Botify
        # cannot unlock writes to this tenant's custom models on its own.
        "allow_custom_models": params.get_param("botify_agent.allow_custom_models")
        in ("True", "true", "1", True),
    }


def missing_config_fields(cfg):
    return [
        label
        for key, label in (
            ("secret", "Shared secret"),
            ("agent_id", "Botify agent ID"),
            ("installation_id", "Botify connection ID"),
        )
        if not cfg[key]
    ]


def verify_transport(cfg, headers, raw_body):
    """Transport HMAC, accepting the current secret or — within a grace
    window after rotation — the previous one. Raises ValueError on failure.
    Secure rotation (AC-25): an operator can rotate the shared secret without
    an outage window where every in-flight Botify replica is instantly
    rejected."""
    ts = headers.get("X-Botify-Timestamp", "")
    sig = headers.get("X-Botify-Signature", "")
    try:
        botify_security.verify_request(cfg["secret"], ts, raw_body, sig)
        return
    except ValueError as primary_exc:
        if not cfg["secret_previous"] or not cfg["secret_rotated_at"]:
            raise primary_exc
        import time as _time

        try:
            rotated_at = float(cfg["secret_rotated_at"])
        except (TypeError, ValueError):
            raise primary_exc
        if _time.time() - rotated_at > cfg["secret_grace_hours"] * 3600:
            raise primary_exc
        # Grace window still open — try the previous secret before failing.
        botify_security.verify_request(cfg["secret_previous"], ts, raw_body, sig)


def json_response(payload, status=200):
    return request.make_response(
        json.dumps(payload),
        headers=[("Content-Type", "application/json; charset=utf-8")],
        status=status,
    )


def error(message, status=400, name=None):
    body = {"error": {"message": message}}
    if name:
        body["error"]["name"] = name
    return json_response(body, status=status)


def user_all_groups(user):
    """A user's groups + implied groups, across Odoo versions (18 vs 19)."""
    if "all_group_ids" in user._fields:
        return user.all_group_ids
    return user.groups_id


def check_access(records, operation):
    checker = getattr(records, "check_access", None)
    if callable(checker):
        checker(operation)
        return
    records.check_access_rights(operation)
    records.check_access_rule(operation)


def extract_write_fields(method, kwargs_in):
    """Field names a create/write call would touch, for the policy check.
    Returns [] for any other method (policy field checks only apply to
    create/write)."""
    if method == "write":
        vals = kwargs_in.get("vals")
        return [f for f in vals.keys() if isinstance(f, str)] if isinstance(vals, dict) else []
    if method == "create":
        vals_list = kwargs_in.get("vals_list")
        fields = set()
        for vals in vals_list if isinstance(vals_list, list) else []:
            if isinstance(vals, dict):
                fields.update(f for f in vals.keys() if isinstance(f, str))
        return list(fields)
    return []


def sanitize_ids(raw):
    if not isinstance(raw, list):
        return []
    return [int(i) for i in raw if isinstance(i, (int, str)) and str(i).isdigit()]


def sanitize_company_ids(raw):
    return sanitize_ids(raw)

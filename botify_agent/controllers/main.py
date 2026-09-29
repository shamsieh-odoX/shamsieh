"""Endpoints the module's own web-client JS calls, as the logged-in employee.

The Odoo browser relay is a capability transport, not an authorization
bypass: an operation runs only with a Botify grant bound to this exact Odoo
session, and then only with the employee's own Odoo rights.
"""

import hmac
import logging
import time

from psycopg2 import IntegrityError

from odoo import http
from odoo.http import request

from ..services import classify, config, errors, executor, grant, guard
from ..services.errors import OperationError

_logger = logging.getLogger(__name__)


def _failure(exception):
    return {"ok": False, "error": errors.normalize(exception)}


def _available(env):
    settings = config.get_settings(env)
    secret = config.get_secret(env)
    if not config.configured(env):
        raise OperationError("INTEGRATION_DISABLED", "the Botify agent is not enabled in this Odoo")
    if not env.user.has_group("botify_agent.group_botify_user"):
        raise OperationError("ACCESS_DENIED", "you are not allowed to use the Botify agent")
    return settings, secret


class BotifyAgentController(http.Controller):
    @http.route("/botify_agent/v1/identity", type="jsonrpc", auth="user", methods=["POST"])
    def identity(self, **_ignored):
        """A fresh, short-lived assertion of who the employee is, for Botify."""
        try:
            guard.check(request)
            settings, secret = _available(request.env)
            user = request.env.user
            company = request.env.company
            claims = {
                "iss": settings["installation_key"],
                "db": request.db,
                "uid": user.id,
                "partner_id": user.partner_id.id or None,
                "name": (user.name or "")[:120],
                "company_id": company.id or None,
                "company_name": (company.name or "")[:120],
                "allowed_company_ids": user.company_ids.ids[:100],
                "sb": grant.session_binding(secret, request.session.sid),
            }
            if user.lang:
                claims["lang"] = user.lang[:16]
            if user.tz:
                claims["tz"] = user.tz[:64]
            token, payload = grant.sign_assertion(secret, claims)
            return {
                "ok": True,
                "result": {
                    "assertion": token,
                    "expiresAt": payload["exp"],
                    "loaderUrl": "%s/widget/v1/widget.js" % settings["api_url"],
                    "siteKey": settings["installation_key"],
                },
            }
        except OperationError as refusal:
            return _failure(refusal)

    @http.route("/botify_agent/v1/events/pending", type="jsonrpc", auth="user", methods=["POST"])
    def events_pending(self, **_ignored):
        """The logged-in employee's own undelivered events, signed for Botify."""
        try:
            guard.check(request)
            settings, secret = _available(request.env)
            events = request.env["botify.agent.event"]._lease(request.env.user)
            tokens = [grant.sign_event(secret, event._token_payload(settings, request.db)) for event in events]
            return {"ok": True, "result": {"events": tokens}}
        except OperationError as refusal:
            return _failure(refusal)

    @http.route("/botify_agent/v1/events/ack", type="jsonrpc", auth="user", methods=["POST"])
    def events_ack(self, acks=None, **_ignored):
        """Botify's signed receipts; only receipts for this employee's own events count."""
        try:
            guard.check(request)
            settings, secret = _available(request.env)
            if not isinstance(acks, list) or len(acks) > 20:
                raise OperationError("INVALID_ARGUMENTS", "acks must be a list of at most 20 receipts")
            env = request.env
            acknowledged = 0
            for token in acks:
                try:
                    ack = grant.verify_ack(token, secret)
                except grant.TokenError as error:
                    _logger.warning("botify_agent: refused event receipt for uid %s: %s", env.uid, error)
                    continue
                if not (ack["iss"] == settings["installation_key"] and ack["db"] == request.db and ack["uid"] == env.uid):
                    _logger.warning("botify_agent: event receipt for another installation or user, uid %s", env.uid)
                    continue
                if env["botify.agent.event"]._acknowledge(env.user, ack):
                    acknowledged += 1
            return {"ok": True, "result": {"acknowledged": acknowledged}}
        except OperationError as refusal:
            return _failure(refusal)

    @http.route("/botify_agent/v1/execute", type="jsonrpc", auth="user", methods=["POST"])
    def execute(self, grant_token=None, context=None, **_ignored):
        """Executes exactly the operation signed into a Botify grant, once."""
        started = time.monotonic()
        env = request.env
        try:
            guard.check(request)
            settings, secret = _available(env)
            granted = self._verified(grant_token, secret, settings)
            stored = env["botify.agent.operation"].claimed(granted["callId"])
            if stored and stored.user_id.id != env.uid:
                raise OperationError("GRANT_REJECTED", "this operation belongs to another user")
            if stored and stored.status != "aborted":
                # Single use: a replay gets the first answer, never a second execution.
                answer = stored.answer()
                if answer is None:
                    raise OperationError("CONFLICT", "this operation is still running")
                return dict(answer, replayed=True)
        except OperationError as refusal:
            # Before a verified grant there is no trustworthy callId to audit under.
            if refusal.code in ("GRANT_REJECTED", "CSRF_FAILED"):
                _logger.warning("botify_agent: refused operation for uid %s: %s", env.uid, refusal)
            return _failure(refusal)

        try:
            with env.cr.savepoint():
                row = env["botify.agent.operation"].claim(granted, env, aborted=stored)
        except IntegrityError:
            return _failure(OperationError("CONFLICT", "this operation is already running"))

        client = None
        try:
            # Refusals and failures roll back only this savepoint; the audit row stays.
            with env.cr.savepoint():
                operation = executor.check_operation(env, dict(granted["op"]))
                scoped = executor.scoped_env(env, context)
                self._authorize_class(scoped, operation, granted, settings)
                result, client = executor.run(scoped, operation)
            answer = {"ok": True, "result": result}
        except Exception as failure:  # noqa: BLE001 - every failure is normalized and audited
            answer = _failure(failure)
        row.finish(answer, int((time.monotonic() - started) * 1000))
        return dict(answer, client=client) if client else answer

    @staticmethod
    def _verified(token, secret, settings):
        try:
            granted = grant.verify_grant(token, secret)
        except grant.TokenError as error:
            raise OperationError("GRANT_REJECTED", str(error)) from error
        bound = (
            granted["iss"] == settings["installation_key"]
            and granted["db"] == request.db
            and granted["uid"] == request.env.uid
            and hmac.compare_digest(granted["sb"], grant.session_binding(secret, request.session.sid))
        )
        if not bound:
            raise OperationError("GRANT_REJECTED", "this operation was granted for another Odoo session")
        if granted["riskClass"] not in classify.RANK:
            raise OperationError("GRANT_REJECTED", "unknown risk class")
        return granted

    @staticmethod
    def _authorize_class(env, operation, granted, settings):
        """This database's own classification: never weaker than the grant's,
        and enabled here too (Botify's rollout can only restrict)."""
        try:
            risk = classify.classify(env, operation)
        except classify.Refused as refusal:
            raise OperationError(refusal.code, str(refusal)) from refusal
        # The grant must be strictly stricter or the very same class: a financial
        # change is not covered by a grant for another top class (destructive).
        if risk != granted["riskClass"] and classify.RANK[risk] >= classify.RANK[granted["riskClass"]]:
            raise OperationError("GRANT_REJECTED", "Odoo classifies this operation as %s" % risk)
        for risk_class in {risk, granted["riskClass"]}:
            if risk_class not in settings["enabled_classes"]:
                raise OperationError("RISK_CLASS_DISABLED", "%s operations are not enabled in this Odoo" % risk_class)

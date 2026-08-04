"""Identity-assertion tests.

Covers the minting side: that the subject comes from the server's own session,
that the token is well-formed and short-lived, and that forged or altered
tokens fail verification.
"""

import json
import time

from odoo.tests import common, tagged

from ..models import botify_security


@tagged("post_install", "-at_install", "botify_agent")
class TestAssertionSigning(common.TransactionCase):
    SECRET = "test-secret-value-do-not-use-in-production"

    def _payload(self, **overrides):
        now = int(time.time())
        payload = {
            "iss": "odoo:testdb",
            "sub": "7",
            "aud": "agent-uuid",
            "bi": "connection-uuid",
            "jti": botify_security.new_nonce(),
            "iat": now,
            "exp": now + 120,
        }
        payload.update(overrides)
        return payload

    def test_roundtrip(self):
        token = botify_security.sign_jwt(self._payload(), self.SECRET)
        decoded = botify_security.verify_jwt(token, self.SECRET)
        self.assertEqual(decoded["sub"], "7")
        self.assertEqual(decoded["aud"], "agent-uuid")

    def test_wrong_secret_rejected(self):
        token = botify_security.sign_jwt(self._payload(), self.SECRET)
        with self.assertRaises(ValueError):
            botify_security.verify_jwt(token, "not-the-secret")

    def test_expired_rejected(self):
        token = botify_security.sign_jwt(
            self._payload(iat=int(time.time()) - 600, exp=int(time.time()) - 60),
            self.SECRET,
        )
        with self.assertRaises(ValueError):
            botify_security.verify_jwt(token, self.SECRET)

    def test_tampered_subject_rejected(self):
        """Editing the uid in the payload must break the signature.

        This is the impersonation attempt an employee would actually make:
        decode the token, change `sub` to a manager's uid, re-encode.
        """
        token = botify_security.sign_jwt(self._payload(), self.SECRET)
        header_b64, payload_b64, signature_b64 = token.split(".")
        payload = json.loads(botify_security._b64url_decode(payload_b64))
        payload["sub"] = "1"
        forged_payload = botify_security._b64url_encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )
        forged = "{}.{}.{}".format(header_b64, forged_payload, signature_b64)
        with self.assertRaises(ValueError):
            botify_security.verify_jwt(forged, self.SECRET)

    def test_alg_none_rejected(self):
        """`alg: none` must never be honoured."""
        payload = self._payload()
        header = botify_security._b64url_encode(
            json.dumps({"alg": "none", "typ": "JWT"}, separators=(",", ":"), sort_keys=True).encode()
        )
        body = botify_security._b64url_encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )
        with self.assertRaises(ValueError):
            botify_security.verify_jwt("{}.{}.".format(header, body), self.SECRET)

    def test_malformed_rejected(self):
        for bad in ("", "a", "a.b", "not-a-token"):
            with self.assertRaises(ValueError):
                botify_security.verify_jwt(bad, self.SECRET)

    def test_nonces_are_unique(self):
        nonces = {botify_security.new_nonce() for _ in range(256)}
        self.assertEqual(len(nonces), 256)


@tagged("post_install", "-at_install", "botify_agent")
class TestIdentityController(common.HttpCase):
    """The controller must derive the subject from the session, not the request."""

    def setUp(self):
        super().setUp()
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("botify_agent.enabled", "True")
        params.set_param("botify_agent.base_url", "https://api.example.test")
        params.set_param("botify_agent.agent_id", "agent-uuid")
        params.set_param("botify_agent.installation_id", "connection-uuid")
        params.set_param("botify_agent.shared_secret", "test-secret-value-do-not-use")
        params.set_param("botify_agent.assertion_ttl", "120")

        self.employee = self.env["res.users"].create({
            "name": "Assertion Employee",
            "login": "botify.assertion@example.com",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })

    def test_assertion_subject_is_the_session_user(self):
        self.authenticate("botify.assertion@example.com", "botify.assertion@example.com")
        response = self.url_open(
            "/botify_agent/identity",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {}}),
            headers={"Content-Type": "application/json"},
        )
        result = response.json().get("result") or {}
        self.assertNotIn("error", result, result.get("error"))

        decoded = botify_security.verify_jwt(
            result["assertion"], "test-secret-value-do-not-use"
        )
        self.assertEqual(
            decoded["sub"],
            str(self.employee.id),
            "the subject must be the authenticated session user",
        )
        self.assertEqual(decoded["aud"], "agent-uuid")
        self.assertEqual(decoded["bi"], "connection-uuid")
        self.assertLessEqual(decoded["exp"] - decoded["iat"], 300)

    def test_anonymous_request_is_rejected(self):
        """auth='user' must keep logged-out callers out entirely."""
        response = self.url_open(
            "/botify_agent/identity",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {}}),
            headers={"Content-Type": "application/json"},
        )
        body = response.json()
        # Odoo answers an unauthenticated json route with a session error rather
        # than a signed assertion — the important part is that no assertion is
        # minted.
        self.assertNotIn("assertion", json.dumps(body))

    def test_client_cannot_choose_the_subject(self):
        """Passing a uid in the request body must not change the subject."""
        self.authenticate("botify.assertion@example.com", "botify.assertion@example.com")
        response = self.url_open(
            "/botify_agent/identity",
            data=json.dumps({
                "jsonrpc": "2.0",
                "method": "call",
                "params": {"uid": 1, "sub": "1", "user_id": 1},
            }),
            headers={"Content-Type": "application/json"},
        )
        result = response.json().get("result") or {}
        decoded = botify_security.verify_jwt(
            result["assertion"], "test-secret-value-do-not-use"
        )
        self.assertEqual(
            decoded["sub"],
            str(self.employee.id),
            "supplying a uid in the body must be ignored",
        )

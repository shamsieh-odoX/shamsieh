import json
import os

from odoo.tests import BaseCase, tagged

from ..services import grant

with open(os.path.join(os.path.dirname(__file__), "vectors.json"), encoding="utf-8") as handle:
    VECTORS = json.load(handle)


@tagged("post_install", "-at_install")
class TestSharedCrypto(BaseCase):
    """The same vectors are checked by packages/connectors/odoo/src/grant.test.ts."""

    def test_verifies_botify_grants(self):
        verified = grant.verify_grant(VECTORS["grantToken"], VECTORS["secret"], now=VECTORS["now"])
        self.assertEqual(verified, VECTORS["grant"])

    def test_signs_assertions_botify_verifies(self):
        token = grant._sign(grant.derive_key(VECTORS["secret"], "identity"), "o1", VECTORS["assertion"])
        self.assertEqual(token, VECTORS["assertionToken"])

    def test_session_binding_survives_soft_rotation(self):
        self.assertEqual(grant.session_binding(VECTORS["secret"], VECTORS["sid"]), VECTORS["sb"])
        rotated = VECTORS["sid"][:42] + "another-random-tail"
        self.assertEqual(grant.session_binding(VECTORS["secret"], rotated), VECTORS["sb"])
        self.assertNotEqual(grant.session_binding(VECTORS["secret"], "B" * 64), VECTORS["sb"])

    def test_refuses_tampering_expiry_and_purpose_confusion(self):
        token, secret, now = VECTORS["grantToken"], VECTORS["secret"], VECTORS["now"]
        prefix, body, mac = token.split(".")
        forged = grant._b64(json.dumps(dict(VECTORS["grant"], uid=1)).encode())
        with self.assertRaisesRegex(grant.TokenError, "bad signature"):
            grant.verify_grant("%s.%s.%s" % (prefix, forged, mac), secret, now=now)
        with self.assertRaisesRegex(grant.TokenError, "bad signature"):
            grant.verify_grant(token, "wss_another_secret", now=now)
        with self.assertRaisesRegex(grant.TokenError, "expired"):
            grant.verify_grant(token, secret, now=VECTORS["grant"]["exp"])
        # An identity assertion is never an operation grant.
        with self.assertRaises(grant.TokenError):
            grant.verify_grant("g1." + VECTORS["assertionToken"].split(".", 1)[1], secret, now=now)

    def test_signs_events_botify_verifies_and_verifies_its_acks(self):
        event = {k: v for k, v in VECTORS["event"].items() if k not in ("v", "iat", "exp")}
        self.assertEqual(grant.sign_event(VECTORS["secret"], event, now=VECTORS["now"]), VECTORS["eventToken"])
        self.assertEqual(grant.verify_ack(VECTORS["ackToken"], VECTORS["secret"], now=VECTORS["now"]), VECTORS["ack"])

    def test_refuses_forged_expired_and_cross_purpose_acks(self):
        token, secret, now = VECTORS["ackToken"], VECTORS["secret"], VECTORS["now"]
        prefix, _body, mac = token.split(".")
        forged = grant._b64(json.dumps(dict(VECTORS["ack"], uid=1)).encode())
        with self.assertRaisesRegex(grant.TokenError, "bad signature"):
            grant.verify_ack("%s.%s.%s" % (prefix, forged, mac), secret, now=now)
        with self.assertRaisesRegex(grant.TokenError, "expired"):
            grant.verify_ack(token, secret, now=VECTORS["ack"]["exp"])
        # The module's own event token is never an ack.
        with self.assertRaises(grant.TokenError):
            grant.verify_ack("a1." + VECTORS["eventToken"].split(".", 1)[1], secret, now=now)

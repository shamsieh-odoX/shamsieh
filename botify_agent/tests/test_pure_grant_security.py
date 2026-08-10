"""Stdlib-only tests for the grant-signing / delegation-proof primitives
added to botify_security.py for the enterprise rebuild.
"""

import sys
import os
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "models"))

import botify_security as sec  # noqa: E402


class TestGrantSigning(unittest.TestCase):
    def test_sign_and_verify_roundtrip(self):
        key = sec.new_secret()
        now = int(time.time())
        claims = {
            "iss": "odoo:testdb",
            "bi": "conn-1",
            "aud": "agent-1",
            "sub": 7,
            "cids": [1],
            "scopes": ["read"],
            "oph": "abc123",
            "jti": sec.new_nonce(),
            "iat": now,
            "exp": now + 60,
        }
        token = sec.sign_grant(claims, key)
        verified = sec.verify_grant(token, key)
        self.assertEqual(verified["sub"], 7)
        self.assertEqual(verified["oph"], "abc123")

    def test_verify_rejects_wrong_key(self):
        key = sec.new_secret()
        other = sec.new_secret()
        now = int(time.time())
        token = sec.sign_grant({"exp": now + 60, "sub": 1}, key)
        with self.assertRaises(ValueError):
            sec.verify_grant(token, other)

    def test_verify_rejects_expired_grant(self):
        key = sec.new_secret()
        now = int(time.time())
        token = sec.sign_grant({"exp": now - 10, "sub": 1}, key)
        with self.assertRaises(ValueError):
            sec.verify_grant(token, key)

    def test_verify_rejects_alg_none(self):
        key = sec.new_secret()
        import base64
        import json

        header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(json.dumps({"exp": 9999999999}).encode()).rstrip(b"=").decode()
        forged = "{}.{}.".format(header, payload)
        with self.assertRaises(ValueError):
            sec.verify_grant(forged, key)


class TestDelegationProof(unittest.TestCase):
    def test_valid_proof_accepted(self):
        key = sec.new_secret()
        ts = str(int(time.time()))
        body = b'{"model":"res.partner"}'
        proof = sec.hmac_hex(key, "{}.{}".format(ts, body.decode("utf-8")))
        sec.verify_delegation_proof(key, ts, body, proof)  # no raise

    def test_proof_with_wrong_key_rejected(self):
        key = sec.new_secret()
        other = sec.new_secret()
        ts = str(int(time.time()))
        body = b'{"model":"res.partner"}'
        proof = sec.hmac_hex(other, "{}.{}".format(ts, body.decode("utf-8")))
        with self.assertRaises(ValueError):
            sec.verify_delegation_proof(key, ts, body, proof)

    def test_stale_proof_rejected(self):
        key = sec.new_secret()
        ts = str(int(time.time()) - 3600)
        body = b'{"model":"res.partner"}'
        proof = sec.hmac_hex(key, "{}.{}".format(ts, body.decode("utf-8")))
        with self.assertRaises(ValueError):
            sec.verify_delegation_proof(key, ts, body, proof)

    def test_tampered_body_rejected(self):
        key = sec.new_secret()
        ts = str(int(time.time()))
        body = b'{"model":"res.partner"}'
        proof = sec.hmac_hex(key, "{}.{}".format(ts, body.decode("utf-8")))
        tampered_body = b'{"model":"account.move"}'
        with self.assertRaises(ValueError):
            sec.verify_delegation_proof(key, ts, tampered_body, proof)


if __name__ == "__main__":
    unittest.main()

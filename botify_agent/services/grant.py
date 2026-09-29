"""Crypto shared with Botify (packages/connectors/odoo/src/grant.ts).

One installation secret; purpose-separated keys derived from it, so an
identity assertion can never be replayed as an operation grant, nor the
reverse. Tokens are ``<prefix>.<base64url(json)>.<base64url(hmac)>``.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

KEY_PURPOSES = {
    "identity": b"botify-odoo-identity-v1",
    "grant": b"botify-odoo-grant-v1",
    "session": b"botify-odoo-session-v1",
    "notification": b"botify-odoo-notification-v1",
    "ack": b"botify-odoo-notification-ack-v1",
}
ASSERTION_LIFETIME = 60
GRANT_MAX_BYTES = 48000
NOTIFICATION_LIFETIME = 300
ACK_MAX_BYTES = 2048
CLOCK_SKEW = 60
# Odoo keeps the first 42 characters of a session id across soft rotations
# (odoo/http.py STORED_SESSION_BYTES); a logout changes them.
SESSION_STATIC_CHARS = 42


class TokenError(Exception):
    pass


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def derive_key(secret, purpose):
    return hmac.new(secret.encode(), KEY_PURPOSES[purpose], hashlib.sha256).digest()


def session_binding(secret, sid):
    """Binds a token to one Odoo login; the session id itself never leaves Odoo."""
    static = (sid or "")[:SESSION_STATIC_CHARS]
    return _b64(hmac.new(derive_key(secret, "session"), static.encode(), hashlib.sha256).digest())


def _sign(key, prefix, payload):
    body = "%s.%s" % (prefix, _b64(json.dumps(payload, separators=(",", ":")).encode()))
    return "%s.%s" % (body, _b64(hmac.new(key, body.encode(), hashlib.sha256).digest()))


def _open(key, prefix, token, max_length):
    if not isinstance(token, str) or len(token) > max_length:
        raise TokenError("token too long")
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != prefix:
        raise TokenError("malformed token")
    expected = hmac.new(key, ("%s.%s" % (prefix, parts[1])).encode(), hashlib.sha256).digest()
    try:
        given = _unb64(parts[2])
    except ValueError as error:
        raise TokenError("malformed token") from error
    if not hmac.compare_digest(given, expected):
        raise TokenError("bad signature")
    try:
        payload = json.loads(_unb64(parts[1]))
    except ValueError as error:
        raise TokenError("malformed payload") from error
    if not isinstance(payload, dict):
        raise TokenError("malformed payload")
    return payload


def sign_assertion(secret, claims, now=None):
    """A short-lived, single-use statement of who the employee is (for Botify)."""
    now = int(now if now is not None else time.time())
    payload = dict(claims, iat=now, exp=now + ASSERTION_LIFETIME, nonce=secrets.token_urlsafe(18))
    return _sign(derive_key(secret, "identity"), "o1", payload), payload


def sign_grant(secret, grant):
    """Botify's side (and the tests'): the module itself only verifies grants."""
    return _sign(derive_key(secret, "grant"), "g1", grant)


def verify_grant(token, secret, now=None):
    """Signature and lifetime; the caller checks the binding to this session."""
    grant = _open(derive_key(secret, "grant"), "g1", token, GRANT_MAX_BYTES)
    now = int(now if now is not None else time.time())
    if grant.get("v") != 1:
        raise TokenError("unsupported grant version")
    for key in ("iss", "callId", "runId", "sessionId", "db", "sb", "riskClass"):
        if not isinstance(grant.get(key), str) or not grant[key]:
            raise TokenError("invalid grant")
    if not isinstance(grant.get("uid"), int) or not isinstance(grant.get("op"), dict):
        raise TokenError("invalid grant")
    exp, iat = grant.get("exp"), grant.get("iat")
    if not isinstance(exp, int) or not isinstance(iat, int):
        raise TokenError("invalid grant")
    if exp <= now:
        raise TokenError("grant expired")
    if iat > now + CLOCK_SKEW or exp - iat > 120:
        raise TokenError("grant lifetime invalid")
    return grant


def sign_event(secret, event, now=None):
    """A notification event for the logged-in employee, relayed by their browser to Botify."""
    now = int(now if now is not None else time.time())
    payload = dict(event, v=1, iat=now, exp=now + NOTIFICATION_LIFETIME)
    return _sign(derive_key(secret, "notification"), "n1", payload)


def verify_ack(token, secret, now=None):
    """Botify's receipt for one event: signature and lifetime; the caller checks the binding."""
    ack = _open(derive_key(secret, "ack"), "a1", token, ACK_MAX_BYTES)
    now = int(now if now is not None else time.time())
    if ack.get("v") != 1 or ack.get("outcome") not in ("delivered", "rejected"):
        raise TokenError("invalid ack")
    for key in ("iss", "db", "eventId"):
        if not isinstance(ack.get(key), str) or not ack[key]:
            raise TokenError("invalid ack")
    exp, iat, uid = ack.get("exp"), ack.get("iat"), ack.get("uid")
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in (exp, iat, uid)):
        raise TokenError("invalid ack")
    if exp <= now:
        raise TokenError("ack expired")
    if iat > now + CLOCK_SKEW or exp - iat > NOTIFICATION_LIFETIME:
        raise TokenError("ack lifetime invalid")
    return ack

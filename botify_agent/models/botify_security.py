"""Signing / verification primitives shared by the Botify controllers.

Deliberately stdlib-only (``hmac``, ``hashlib``, ``base64``, ``json``, ``secrets``).
PyJWT ships with some Odoo builds and not others, and a hard dependency that is
present on odoo.sh but missing on a customer's self-hosted box is a support
problem we do not need for ~40 lines of HS256.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

# Signature comparisons always go through hmac.compare_digest: a plain ``==`` on
# a MAC leaks its prefix through timing and is the classic way these get broken.


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def sign_jwt(payload: dict, secret: str) -> str:
    """Mint a compact HS256 JWS.

    The header is fixed to HS256 — we never emit ``alg: none``, and the verifier
    on the Botify side pins the algorithm rather than trusting this header.
    """
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = "{}.{}".format(
        _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode()),
        _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()),
    )
    signature = hmac.new(
        secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest()
    return "{}.{}".format(signing_input, _b64url_encode(signature))


def verify_jwt(token: str, secret: str) -> dict:
    """Verify an HS256 JWS and return its payload. Raises ValueError on any fault."""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError:
        raise ValueError("malformed token")

    header = json.loads(_b64url_decode(header_b64))
    # Pin the algorithm. Accepting the token's own ``alg`` is what enables the
    # "alg: none" and HMAC-vs-RSA confusion attacks.
    if header.get("alg") != "HS256":
        raise ValueError("unexpected algorithm")

    expected = hmac.new(
        secret.encode("utf-8"),
        "{}.{}".format(header_b64, payload_b64).encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected, _b64url_decode(signature_b64)):
        raise ValueError("bad signature")

    payload = json.loads(_b64url_decode(payload_b64))
    now = int(time.time())
    if int(payload.get("exp", 0)) < now:
        raise ValueError("expired")
    return payload


def sign_request(secret: str, timestamp: str, raw_body: bytes) -> str:
    """HMAC over ``<timestamp>.<body>`` — the scheme Botify's client mirrors.

    Binding the timestamp into the MAC is what makes the freshness window
    meaningful: an attacker cannot take a captured body and re-stamp it.
    """
    message = timestamp.encode("ascii") + b"." + raw_body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_request(secret: str, timestamp: str, raw_body: bytes, provided: str,
                   max_skew_seconds: int = 300) -> None:
    """Verify a Botify -> Odoo call. Raises ValueError on any fault."""
    if not timestamp or not provided:
        raise ValueError("missing signature headers")
    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError):
        raise ValueError("bad timestamp")

    # Freshness window: bounds how long a captured request stays replayable.
    if abs(int(time.time()) - sent_at) > max_skew_seconds:
        raise ValueError("stale request")

    expected = sign_request(secret, timestamp, raw_body)
    supplied = provided[len("sha256="):] if provided.startswith("sha256=") else provided
    if not hmac.compare_digest(expected, supplied):
        raise ValueError("bad signature")


def new_nonce() -> str:
    return secrets.token_urlsafe(18)


def new_secret() -> str:
    """A fresh, high-entropy key for delegation credentials and grant-signing keys."""
    return secrets.token_urlsafe(32)


def sign_grant(claims: dict, grant_key: str) -> str:
    """Mint the per-operation grant JWS. Same HS256 primitive as sign_jwt —
    kept as a distinct name because the KEY is different (a grant-signing key
    that never leaves Odoo, generated on first use and stored in
    ir.config_parameter, separate from the installation shared secret) and
    because grant claims are shaped differently (sub=uid, oph=operation hash,
    much shorter exp)."""
    return sign_jwt(claims, grant_key)


def verify_grant(token: str, grant_key: str) -> dict:
    """Verify a grant JWS and return its claims. Raises ValueError on any fault."""
    return verify_jwt(token, grant_key)


def hmac_hex(key: str, message: str) -> str:
    return hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_delegation_proof(delegation_key: str, timestamp: str, raw_body: bytes, provided: str,
                             max_skew_seconds: int = 60) -> None:
    """Verify Botify's proof of possession of a delegation key on a grant
    request. Deliberately a SHORTER skew window than verify_request's 300s:
    a grant request is minted fresh per tool call, not held and reused, so a
    tight window meaningfully shrinks the replay-capture surface even before
    the jti-based defence at execution time."""
    if not timestamp or not provided:
        raise ValueError("missing delegation proof headers")
    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError):
        raise ValueError("bad timestamp")
    if abs(int(time.time()) - sent_at) > max_skew_seconds:
        raise ValueError("stale delegation proof")
    expected = hmac_hex(delegation_key, "{}.{}".format(timestamp, raw_body.decode("utf-8")))
    supplied = provided[len("sha256="):] if provided.startswith("sha256=") else provided
    if not hmac.compare_digest(expected, supplied):
        raise ValueError("bad delegation proof")

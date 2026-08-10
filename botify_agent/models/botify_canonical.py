"""Deterministic operation-hash ("oph") canonicalisation.

Stdlib-only, deliberately independent of Odoo and of Python's own ``json``
module's serialisation choices (key order, whitespace, ``ensure_ascii``) —
this MUST produce byte-identical output to
``packages/api/src/services/odoo/policy/operationHash.ts``'s
``canonicalJson`` / ``computeOperationHash``. A grant token binds ``oph`` to
the exact intended operation; this module recomputes it from the actual
request body at execution time, and a mismatch is rejected as
``grant_operation_mismatch``. A divergence between the two implementations
either breaks every call (availability) or lets a grant for one operation be
silently reinterpreted as authorizing a different one (security) — hence the
golden-vector tests in ``tests/test_pure_canonical.py``, checked against the
identical fixed vectors used by ``operationHash.test.ts`` (not derived from
either implementation's own output).
"""

import hashlib


def canonical_json(value):
    """Mirrors operationHash.ts:canonicalJson exactly. See module docstring."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            return "null"
        if isinstance(value, float) and value.is_integer():
            # JS `String(20)` -> "20", not "20.0" — align Python's float
            # formatting with JS's Number->String for whole-valued floats.
            return str(int(value))
        return str(value)
    if isinstance(value, str):
        return _canonical_string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_json(v) for v in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value.keys())
        return "{" + ",".join(f"{_canonical_string(k)}:{canonical_json(value[k])}" for k in keys) + "}"
    return "null"


def _canonical_string(s):
    out = ['"']
    for ch in s:
        code = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif code < 0x20:
            out.append("\\u%04x" % code)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def sha256hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def operation_hash(model, method, ids=None, domain=None, kwargs=None):
    sorted_ids = sorted(int(i) for i in (ids or []))
    domain_hash = sha256hex(canonical_json(domain if domain is not None else []))
    kwargs_hash = sha256hex(canonical_json(kwargs if kwargs is not None else {}))
    material = "{}|{}|{}|{}|{}".format(
        model,
        method,
        ",".join(str(i) for i in sorted_ids),
        domain_hash,
        kwargs_hash,
    )
    return sha256hex(material)

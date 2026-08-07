"""Shared Odoo policy manifest loader + deny-by-default evaluator.

Stdlib-only (``json``, ``hashlib``, ``re``), no Odoo import — mirrors
packages/api/src/services/odoo/policy/{manifest,decision}.ts exactly. Both
sides load a byte-identical copy of
integrations/odoo/policy/policy.manifest.json; MANIFEST_SHA256 pins the
expected hash of THIS package's local copy
(integrations/odoo/botify_agent/data/policy_manifest.json) so a manifest
edit that isn't mirrored to both copies is caught immediately rather than
silently drifting (see threat-model.md ยง3.10).
"""

import hashlib
import json
import os
import re

# Mirrors packages/api/src/services/odoo/policy/tenantModels.ts. Odoo model
# names come in two shapes and BOTH must be accepted, or Studio models become
# permanently unclassifiable: dotted developer-module models
# (``shams.todo.task``) and dot-less Studio models (``x_membership``).
_TENANT_MODEL_NAME_RE = re.compile(r"^(x_[a-z0-9_]+|[a-z][a-z0-9_]*(\.[a-z0-9_]+)+)$")
_TENANT_MAX_MODEL_NAME_LENGTH = 64

# Same regex blacklist as odooDiscovery.ts:SENSITIVE_MODEL_RE. A tenant entry
# naming any of these is refused outright, so the overlay can never be used to
# reach Odoo's infrastructure, auth or messaging models.
_TENANT_RESERVED_RE = re.compile(
    r"^(ir\.|base\.|base_|bus\.|res\.users|res\.groups|res\.config|res\.lang|res\.company\."
    r"|auth[._]|mail\.|sms\.|fetchmail\.|iap[._]|payment\.(token|provider|method)|account\.online"
    r"|auth_totp|change\.password|web[._]|website\.visitor|digest\.)"
)

# Stricter reserved roots for tenant classification only, mirroring
# tenantModels.ts:TENANT_RESERVED_NAMESPACE_RE. Discovery marks a model custom
# when a custom module defines OR EXTENDS it, so on a heavily customised
# database the "custom" set legitimately includes standard Odoo models
# (res.company, resource.calendar.leaves, project.update, ...). The global
# manifest blocks the ones it classifies, but it is finite. `botify.` is here
# because botify.agent.delegation/nonce are this addon's OWN security state
# (delegation credentials and the grant replay guard) and must never be
# reachable through operator-configured policy.
_TENANT_RESERVED_ROOT_RE = re.compile(
    r"^(res\.|resource\.|ir\.|base\.|bus\.|mail\.|web\.|website\.|report\.|botify\."
    r"|account\.|payment\.|uom\.|auth|iap)"
)

VALID_OP_CLASSES = frozenset(
    [
        "read",
        "capture_write",
        "normal_write",
        "financial_write",
        "lifecycle_action",
        "batch_action",
    ]
)

_VALID_WRITE_OP_CLASSES = frozenset(["capture_write", "normal_write", "financial_write"])

_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "policy_manifest.json")

# Update in the SAME commit as any manifest edit.
MANIFEST_SHA256 = "1b86729fa3cabdae3b18644b4fd44317db0a556102958faeecbf04316d749a9f"

RISK_BY_OP_CLASS = {
    "read": "low",
    "capture_write": "low",
    "normal_write": "medium",
    "lifecycle_action": "medium",
    "financial_write": "high",
    "batch_action": "high",
}

_cache = {}


def load_raw_manifest(path=_DATA_PATH):
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    sha256 = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, sha256


def get_policy_manifest(path=_DATA_PATH):
    if path in _cache:
        return _cache[path]
    raw, sha256 = load_raw_manifest(path)
    if sha256 != MANIFEST_SHA256:
        raise ValueError(
            "odoo policy manifest hash mismatch: expected %s, got %s. Refusing to "
            "load a policy manifest that does not match the reviewed constant."
            % (MANIFEST_SHA256, sha256)
        )
    manifest = json.loads(raw)
    _cache[path] = manifest
    return manifest


def sanitize_tenant_model(entry, model, manifest=None):
    """Validate a Botify-supplied classification for ONE custom model.

    Mirrors tenantModels.ts:buildTenantModelMap. Returns a manifest-shaped model
    entry, or None if the entry is absent/malformed/not permissible.

    This is the addon's independent check on data that arrived from Botify. It
    is deliberately not "trust the caller": the global manifest is re-consulted
    here, so a standard model can never be reclassified through this path even
    by a fully compromised Botify. The blast radius is bounded to models Odoo
    itself considers custom, and Odoo's own ACLs/record rules still gate the
    operation afterwards via with_user().
    """
    if not isinstance(entry, dict):
        return None
    if entry.get("model") != model:
        return None
    if not isinstance(model, str) or len(model) > _TENANT_MAX_MODEL_NAME_LENGTH:
        return None
    if not _TENANT_MODEL_NAME_RE.match(model):
        return None
    if _TENANT_RESERVED_RE.match(model) or _TENANT_RESERVED_ROOT_RE.match(model):
        return None

    manifest = manifest or get_policy_manifest()
    # Global manifest supremacy, enforced independently of the Botify side.
    if manifest["models"].get(model):
        return None

    op_classes_raw = entry.get("opClasses")
    if not isinstance(op_classes_raw, list):
        return None
    op_classes = [oc for oc in op_classes_raw if isinstance(oc, str) and oc in VALID_OP_CLASSES]
    if not op_classes:
        return None

    write_op_class = entry.get("writeOpClass")
    if not isinstance(write_op_class, str) or write_op_class not in _VALID_WRITE_OP_CLASSES:
        write_op_class = "normal_write"
    create_op_class = entry.get("createOpClass")
    if not isinstance(create_op_class, str) or create_op_class not in _VALID_WRITE_OP_CLASSES:
        create_op_class = write_op_class

    return {
        "dataClass": "tenant_custom",
        "sensitive": entry.get("sensitive") is True,
        "createOpClass": create_op_class,
        "writeOpClass": write_op_class,
        "opClasses": op_classes,
        "sensitiveFields": [],
    }


class PolicyDenied(Exception):
    def __init__(self, reason, message, op_class=None):
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.op_class = op_class
        self.risk_level = RISK_BY_OP_CLASS.get(op_class, "high") if op_class else "high"


def evaluate(model, method, fields=None, ids=None, batch_size=None, op_class_override=None,
             granted_op_classes=None, manifest=None, tenant_model=None):
    """Deny-by-default evaluation. Raises PolicyDenied, or returns
    {"opClass": ..., "riskLevel": ..., "classificationSource": ...} on success.
    Mirrors decision.ts:evaluate.

    ``tenant_model`` is an already-sanitized entry (see sanitize_tenant_model)
    for one of this tenant's own custom models. It is consulted ONLY when the
    global manifest has no entry for the model, which is what makes global
    manifest supremacy structural here rather than merely validated.
    """
    manifest = manifest or get_policy_manifest()
    granted_op_classes = granted_op_classes if granted_op_classes is not None else set()

    model_entry = manifest["models"].get(model)
    classification_source = "global"
    if not model_entry and tenant_model:
        model_entry = tenant_model
        classification_source = "tenant"
    if not model_entry:
        raise PolicyDenied("model_unclassified", 'Model "%s" is not classified in the policy manifest.' % model)

    if method.startswith("_") or method in manifest["forbiddenMethods"]:
        raise PolicyDenied("method_forbidden", 'Method "%s" is never permitted.' % method)

    if op_class_override:
        op_class = op_class_override
    else:
        method_entry = manifest["methods"].get(method)
        if not method_entry:
            raise PolicyDenied("method_forbidden", 'Method "%s" is not in the policy manifest\'s method map.' % method)
        raw = method_entry["opClass"]
        if raw == "$modelCreateOpClass":
            op_class = model_entry["createOpClass"]
        elif raw == "$modelWriteOpClass":
            op_class = model_entry["writeOpClass"]
        else:
            op_class = raw

    if op_class not in model_entry["opClasses"]:
        raise PolicyDenied(
            "op_class_not_permitted_for_model",
            'Model "%s" does not permit operation class "%s".' % (model, op_class),
            op_class,
        )

    if op_class not in granted_op_classes:
        raise PolicyDenied("scope_not_granted", 'Operation class "%s" is not granted.' % op_class, op_class)

    if fields:
        forbidden_re = re.compile(manifest["forbiddenWriteFieldPattern"], re.IGNORECASE)
        workflow_re = re.compile(manifest["workflowFieldPattern"], re.IGNORECASE)
        for field in fields:
            if not isinstance(field, str):
                continue
            if field.startswith("_") or forbidden_re.search(field):
                raise PolicyDenied(
                    "field_denied", 'Field "%s" cannot be modified through the assistant.' % field, op_class
                )
            # Only a WRITE to an existing record can skip a lifecycle action's
            # side effects (stock reservation, sequence numbers...) -- setting
            # an initial state/stage_id on CREATE is the normal, correct way to
            # start a new record in a given state and must stay allowed. Mirrors
            # decision.ts:evaluate -- keep both in lockstep.
            if method == "write" and workflow_re.match(field):
                raise PolicyDenied(
                    "field_denied",
                    'Field "%s" cannot be set directly \u2014 use the matching lifecycle action instead.' % field,
                    op_class,
                )

    limits = manifest["limits"]
    if batch_size is not None and batch_size > limits["maxBatchSize"]:
        raise PolicyDenied(
            "batch_too_large",
            "Batch of %d exceeds the maximum of %d." % (batch_size, limits["maxBatchSize"]),
            op_class,
        )
    if ids and len(ids) > limits["maxIds"]:
        raise PolicyDenied(
            "too_many_ids", "%d ids exceeds the maximum of %d." % (len(ids), limits["maxIds"]), op_class
        )

    return {
        "opClass": op_class,
        "riskLevel": RISK_BY_OP_CLASS[op_class],
        "classificationSource": classification_source,
    }

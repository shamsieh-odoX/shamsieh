"""The platform risk class of one operation, computed again in Odoo.

Same rules and same baseline (``data/risk_baseline.json``) as Botify's
classifier (packages/connectors/odoo/src/classify.ts), plus this database's
own field rules. A grant whose class is weaker than this one is refused:
classification only ever tightens.
"""

import json
import os

from . import params

RISK_CLASSES = ["read", "low_write", "high_write", "financial", "destructive", "external_communication"]
RANK = {
    "read": 0,
    "low_write": 1,
    "high_write": 2,
    "financial": 3,
    "destructive": 3,
    "external_communication": 3,
}
READ_OPS = {"context", "list_models", "describe_model", "search", "read", "count", "aggregate", "name_search", "open_record"}

with open(os.path.join(os.path.dirname(__file__), "..", "data", "risk_baseline.json"), encoding="utf-8") as handle:
    BASELINE = json.load(handle)


class Refused(Exception):
    """The operation is not allowed at all (``code``: the module error code)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def stricter(a, b):
    return b if RANK[b] > RANK[a] else a


# Two different top-rank classes in one operation (a price change that also
# archives) would need both enabled and confirmed as both: refused, to be split.
MIXED = "mixed_high_risk"


def tighten(a, b):
    if MIXED in (a, b) or (a != b and RANK[a] == RANK[b] == 3):
        return MIXED
    return stricter(a, b)


def _financial_field(name):
    return name in BASELINE["financialFields"] or any(
        name.startswith(prefix) for prefix in BASELINE["financialFieldPrefixes"]
    )


def _financial_model(model):
    return any(model.startswith(prefix) for prefix in BASELINE["financialModelPrefixes"])


def writable_problem(model, name):
    """Why ``name`` can never be written through the agent, or None."""
    if name in BASELINE["refusedFields"]:
        return "field_not_writable:%s" % name
    field = model._fields.get(name)
    if field is None:
        return "unknown_field:%s" % name
    # A stored compute with readonly=False (crm.lead.stage_id) keeps what is written;
    # a non-stored one without inverse silently drops it.
    if field.readonly or (field.compute and not field.inverse and not field.store):
        return "field_not_writable:%s" % name
    if not model._has_field_access(field, "write"):
        return "unknown_field:%s" % name
    return None


def _field_class(env, mode, model, name, value, rules):
    problem = writable_problem(model, name)
    if problem:
        raise Refused("OPERATION_REFUSED", problem)
    field = model._fields[name]
    risk = "low_write"
    listed = BASELINE["fields"].get(model._name, {}).get(name)
    if listed:
        risk = tighten(risk, listed)
    ruled = rules.get((model._name, name))
    if ruled:
        risk = tighten(risk, ruled)
    if _financial_field(name) or field.type == "monetary":
        return tighten(risk, "financial")
    if field.type == "many2one":
        return tighten(risk, "high_write") if mode == "write" else risk
    if field.type in ("one2many", "many2many"):
        return tighten(risk, _commands_class(env, mode, field.comodel_name, name, value, rules))
    if field.type == "selection" and any(name.startswith(p) for p in BASELINE["stateLikeFieldPrefixes"]):
        return tighten(risk, "high_write")
    if field.type in BASELINE["lowRiskFieldTypes"]:
        return risk
    return tighten(risk, "high_write")


def _commands_class(env, mode, relation, name, value, rules):
    if not isinstance(value, list):
        raise Refused("OPERATION_REFUSED", "invalid_x2many_value:%s" % name)
    risk = "high_write" if mode == "write" else "low_write"
    for command in value:
        if not isinstance(command, list) or not command or command[0] not in (0, 1, 2, 3, 4, 5, 6):
            raise Refused("OPERATION_REFUSED", "invalid_x2many_value:%s" % name)
        kind = command[0]
        if kind in (2, 3, 5):
            risk = tighten(risk, "destructive")
        elif kind in (4, 6):
            risk = tighten(risk, "high_write")
        else:
            if len(command) != 3 or not isinstance(command[2], dict):
                raise Refused("OPERATION_REFUSED", "invalid_x2many_value:%s" % name)
            child_mode = "create" if kind == 0 else "write"
            risk = tighten(risk, _values_class(env, child_mode, env[relation], command[2], rules))
    return risk


def _values_class(env, mode, model, values, rules):
    risk = "financial" if _financial_model(model._name) else "low_write"
    if model._name in BASELINE["externalCommunicationModels"]:
        risk = tighten(risk, "external_communication")
    for name, value in values.items():
        # Odoo stores bool(value): 0, None and "" archive as surely as False.
        if name == "active" and not value:
            risk = tighten(risk, "destructive")
            continue
        risk = tighten(risk, _field_class(env, mode, model, name, value, rules))
    return risk


def method_contract(env, model_name, method):
    """(risk class, params schema) of a registered, active method, or None."""
    row = env["botify.agent.method"].search(
        [("model", "=", model_name), ("method", "=", method), ("active", "=", True)], limit=1
    )
    if not row:
        return None
    schema = row.schema()
    baseline = BASELINE["methods"].get(model_name, {}).get(method)
    risk = stricter(row.risk_class, baseline) if baseline else row.risk_class
    return risk, schema, row


def classify(env, operation):
    """The risk class of a (structurally valid) operation for the current user."""
    op = operation["op"]
    if op in READ_OPS:
        return "read"
    model = env[operation["model"]]
    if op == "unlink":
        return "destructive"
    if op == "call":
        contract = method_contract(env, operation["model"], operation["method"])
        if not contract:
            raise Refused("METHOD_NOT_ALLOWED", "method_not_allowed:%s.%s" % (operation["model"], operation["method"]))
        risk, schema, row = contract
        problems = params.validate(schema, operation.get("kwargs", {}))
        if problems:
            raise Refused("INVALID_ARGUMENTS", "; ".join(problems))
        if row.record_arity == "one" and len(operation["ids"]) != 1:
            raise Refused("INVALID_ARGUMENTS", "this action takes exactly one record")
        if len(operation["ids"]) > row.max_records:
            raise Refused("INVALID_ARGUMENTS", "at most %d records" % row.max_records)
        if len(operation["ids"]) > 1:
            risk = stricter(risk, "high_write")
        return risk
    rules = {
        (rule.model, rule.field): rule.risk_class
        for rule in env["botify.agent.field_rule"].search([])
    }
    mode = "create" if op == "create" else "write"
    risk = _values_class(env, mode, model, operation["values"], rules)
    if op == "write" and len(operation["ids"]) > 1:
        risk = tighten(risk, "high_write")
    if risk == MIXED:
        raise Refused("OPERATION_REFUSED", "%s: split it into separate changes" % MIXED)
    return risk

"""Runs one granted operation as the logged-in employee (``request.env.user``).

Hard rules (tested): no ``sudo()`` here, public methods only, CRUD or a
registered business method, no caller-supplied context beyond the
allowlist, generic writes never touch state/company or protected fields.
Odoo's access rights and record rules decide every read and write.
"""

import re

from odoo import fields as odoo_fields

from . import classify
from .errors import OperationError

LIMITS = {"records": 80, "fields": 25, "domain": 50, "in_values": 200, "bulk": 50, "groupby": 3, "values": 40, "text": 20000}
MODEL = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z0-9_]+)*$")
FIELD = re.compile(r"^[a-z_][a-z0-9_]*$")
PATH = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*){0,2}$")
METHOD = re.compile(r"^[a-z][a-z0-9_]*$")
ORDER = re.compile(r"^[a-z_][a-z0-9_]*( (asc|desc))?(, ?[a-z_][a-z0-9_]*( (asc|desc))?){0,4}$", re.I)
GROUPBY = re.compile(r"^[a-z_][a-z0-9_]*(:(day|week|month|quarter|year))?$")
AGGREGATE = re.compile(r"^([a-z_][a-z0-9_]*:(sum|avg|min|max|count_distinct)|__count)$")
OPERATORS = {"=", "!=", ">", ">=", "<", "<=", "like", "ilike", "not like", "not ilike", "=like", "=ilike", "in", "not in", "child_of", "parent_of"}
SKIPPED_MODEL_PREFIXES = ("ir.", "base.", "bus.", "botify.", "res.config", "web_", "_unknown")
ALLOWED_CONTEXT = ("lang", "tz", "allowed_company_ids")


def _refuse(message):
    raise OperationError("VALIDATION_FAILED", message)


def _ids(value, maximum):
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        _refuse("ids must list 1 to %d records" % maximum)
    if not all(isinstance(i, int) and not isinstance(i, bool) and 0 < i < 2**31 for i in value):
        _refuse("ids must be record ids")
    return sorted(set(value))


def _domain(value):
    if not isinstance(value, list) or len(value) > LIMITS["domain"]:
        _refuse("invalid domain")
    for term in value:
        if term in ("&", "|", "!"):
            continue
        if not (isinstance(term, list) and len(term) == 3 and isinstance(term[0], str) and PATH.match(term[0])):
            _refuse("invalid domain term")
        if term[1] not in OPERATORS:
            _refuse("invalid domain operator")
        if isinstance(term[2], list) and len(term[2]) > LIMITS["in_values"]:
            _refuse("too many values in a domain term")
    return value


def _fields(model, names):
    if not isinstance(names, list) or len(names) > LIMITS["fields"]:
        _refuse("at most %d fields" % LIMITS["fields"])
    for name in names:
        if not isinstance(name, str) or not FIELD.match(name):
            _refuse("fields are plain field names")
        if name not in model._fields:
            _refuse("unknown field %s" % name)
        # Odoo raises AccessError for a field the employee may not read.
        model._check_field_access(model._fields[name], "read")
    return names


def _values(values):
    if not isinstance(values, dict) or not 0 < len(values) <= LIMITS["values"]:
        _refuse("values must set 1 to %d fields" % LIMITS["values"])
    for name, value in values.items():
        if not FIELD.match(name):
            _refuse("invalid field name")
        if isinstance(value, str) and len(value) > LIMITS["text"]:
            _refuse("value of %s is too long" % name)
    return values


def check_operation(env, operation):
    """Structural checks (the grant is authentic; this is defence in depth)."""
    op = operation.get("op")
    if op not in classify.READ_OPS and op not in ("create", "write", "unlink", "call"):
        _refuse("unknown operation")
    model = operation.get("model")
    if op not in ("context", "list_models"):
        if not isinstance(model, str) or not MODEL.match(model) or model.startswith(SKIPPED_MODEL_PREFIXES):
            raise OperationError("ACCESS_DENIED", "this model is not available to the agent")
        if model not in env:
            raise OperationError("RECORD_NOT_FOUND", "model %s does not exist" % model)
    if op == "call" and not (isinstance(operation.get("method"), str) and METHOD.match(operation["method"])):
        raise OperationError("METHOD_NOT_ALLOWED", "only public business methods can be called")
    if op in ("write", "unlink", "call"):
        operation["ids"] = _ids(operation.get("ids"), LIMITS["bulk"])
    elif op in ("read", "open_record"):
        operation["ids"] = _ids(operation.get("ids"), LIMITS["records"] if op == "read" else 1)
    if op in ("create", "write"):
        _values(operation.get("values"))
    if op == "call" and not all(
        isinstance(v, (str, int, float, bool)) or v is None for v in (operation.get("kwargs") or {}).values()
    ):
        _refuse("business action arguments are plain values")
    return operation


def scoped_env(env, context):
    """The employee's environment, with only allowlisted context keys.

    ``allowed_company_ids`` must be companies the employee belongs to.
    """
    extra = {key: context[key] for key in ALLOWED_CONTEXT if key in (context or {})}
    companies = extra.get("allowed_company_ids")
    if companies is not None:
        if not isinstance(companies, list) or not companies or not set(companies) <= set(env.user.company_ids.ids):
            raise OperationError("ACCESS_DENIED", "the selected companies are not allowed for this user")
    return env(context=dict(env.context, **extra))


def record_link(record):
    """The web-client URL of a record, generated here only: the form action
    Odoo itself opens for it, on this database's configured base URL (never
    the request's host). The employee's Odoo checks access again on open."""
    action = record.get_formview_action()
    model, res_id = action.get("res_model"), action.get("res_id")
    if action.get("type") != "ir.actions.act_window" or not model or not isinstance(res_id, int) or res_id <= 0:
        return None
    # The web client's router: a dotted model is its own path segment, others take "m-".
    segment = model if "." in model else "m-" + model
    return "%s/odoo/%s/%d" % (record.get_base_url().rstrip("/"), segment, res_id)


def _with_links(model, records):
    for record in records:
        record["url"] = record_link(model.browse(record["id"]))
    return records


def _check_unchanged(records, expected):
    if not expected:
        return
    for record in records:
        if odoo_fields.Datetime.to_string(record.write_date) != expected:
            raise OperationError("RECORD_CHANGED", "%s changed since it was read" % record.display_name)


def _existing(model, ids):
    records = model.browse(ids).exists()
    if len(records) != len(ids):
        raise OperationError("RECORD_NOT_FOUND", "some records do not exist or were deleted")
    records.check_access("read")
    return records


def _json_safe(value):
    if isinstance(value, dict) and value.get("type"):
        # The method opened a wizard or another screen: it needs the employee.
        return {"completed": False, "requiresUserAction": str(value.get("name") or value["type"])[:120]}
    if value is None or isinstance(value, (bool, int, float, str)):
        return {"completed": True, "returned": value if not isinstance(value, str) else value[:500]}
    return {"completed": True}


def _list_models(env, operation):
    query = (operation.get("query") or "")[:100]
    limit = min(int(operation.get("limit") or 30), 50)
    needle = re.sub(r"[\W_]+", "", query.casefold())

    def readable_models(search):
        found = []
        for name in sorted(env.registry.models):
            if name.startswith(SKIPPED_MODEL_PREFIXES):
                continue
            model = env[name]
            if model._abstract or model._transient:
                continue
            label = model._description or name
            if search and (
                search not in re.sub(r"[\W_]+", "", name.casefold())
                and search not in re.sub(r"[\W_]+", "", label.casefold())
            ):
                continue
            if not model.has_access("read"):
                continue
            found.append({"model": name, "name": label})
            if len(found) >= limit:
                break
        return found

    # ir.model records are not readable by every employee even when the
    # business model itself is. Discover from the registry, then filter by the
    # employee's model ACL; record rules still govern every subsequent query.
    found = readable_models(needle)
    if found or not query:
        return {"models": found}
    # Client-action names often differ from their model names (e.g. a
    # "Shamsieh To-Do" page backed by a shams.todo.* model).
    last_word = re.sub(r"[\W_]+", "", query.split()[-1].casefold())
    return {"models": readable_models(last_word) if len(last_word) >= 3 else []}


def describe_model(env, model_name):
    """Fields this employee may read (and whether they may write them) and the allowed methods."""
    model = env[model_name]
    model.check_access("read")
    rules = {rule.field: rule.risk_class for rule in env["botify.agent.field_rule"].search([("model", "=", model_name)])}
    described = {}
    for name, field in model._fields.items():
        if name.startswith("_") or not model._has_field_access(field, "read"):
            continue
        meta = {"type": field.type, "string": field.string}
        if field.relational:
            meta["relation"] = field.comodel_name
        if classify.writable_problem(model, name):
            meta["readonly"] = True
        if field.required:
            meta["required"] = True
        if name in rules:
            meta["riskClass"] = rules[name]
        described[name] = meta
    methods = [
        {"name": row.method, "riskClass": row.risk_class, "description": row.description or row.method, "params": row.schema()}
        for row in env["botify.agent.method"].search([("model", "=", model_name), ("active", "=", True)])
    ]
    title = model._description or model_name
    return {"model": model_name, "name": title, "fields": described, "methods": methods}


def run(env, operation):
    """Executes the operation; returns ``(result, client)`` where ``client`` is
    for the employee's browser only (e.g. the form to open), never for Botify."""
    op = operation["op"]
    if op == "context":
        user = env.user
        return {
            "uid": user.id,
            "name": user.name,
            "company": {"id": env.company.id, "name": env.company.name},
            "companies": [{"id": c.id, "name": c.name} for c in env.companies],
            "lang": env.lang,
            "tz": user.tz,
        }, None
    if op == "list_models":
        return _list_models(env, operation), None
    if op == "describe_model":
        return describe_model(env, operation["model"]), None

    model = env[operation["model"]]
    if op == "search":
        names = _fields(model, operation.get("fields") or ["display_name"])
        order = operation.get("order")
        if order and not ORDER.match(order):
            _refuse("invalid order")
        limit = min(int(operation.get("limit") or 20), LIMITS["records"])
        records = model.search_read(
            _domain(operation.get("domain") or []), names, offset=int(operation.get("offset") or 0), limit=limit, order=order
        )
        return {"records": _with_links(model, records)}, None
    if op == "read":
        records = _existing(model, operation["ids"]).read(_fields(model, operation.get("fields") or ["display_name"]))
        return {"records": _with_links(model, records)}, None
    if op == "count":
        return {"count": model.search_count(_domain(operation.get("domain") or []))}, None
    if op == "aggregate":
        groupby = operation.get("groupby") or []
        aggregates = operation.get("aggregates") or []
        if not 0 < len(groupby) <= LIMITS["groupby"] or not all(isinstance(g, str) and GROUPBY.match(g) for g in groupby):
            _refuse("invalid groupby")
        if not 0 < len(aggregates) <= 10 or not all(isinstance(a, str) and AGGREGATE.match(a) for a in aggregates):
            _refuse("invalid aggregates")
        _fields(model, [g.split(":")[0] for g in groupby] + [a.split(":")[0] for a in aggregates if a != "__count"])
        groups = model.formatted_read_group(
            _domain(operation.get("domain") or []), groupby, aggregates, limit=min(int(operation.get("limit") or 80), 80)
        )
        return {"groups": groups}, None
    if op == "name_search":
        found = model.name_search(str(operation.get("name") or "")[:200], limit=min(int(operation.get("limit") or 8), 20))
        return [{"id": record_id, "display_name": name} for record_id, name in found], None
    if op == "open_record":
        record = _existing(model, operation["ids"])
        return {"id": record.id, "display_name": record.display_name, "url": record_link(record)}, {
            "action": record.get_formview_action()
        }

    if op == "create":
        record = model.create(dict(operation["values"]))
        return {"id": record.id, "display_name": record.display_name, "url": record_link(record)}, None
    if op == "write":
        for name in operation["values"]:
            problem = classify.writable_problem(model, name)
            if problem:
                raise OperationError("OPERATION_REFUSED", problem)
        records = _existing(model, operation["ids"])
        _check_unchanged(records, operation.get("expectedWriteDate"))
        records.write(dict(operation["values"]))
        return {"ids": records.ids, "updated": len(records)}, None
    if op == "unlink":
        records = _existing(model, operation["ids"])
        names = records.mapped("display_name")
        records.unlink()
        return {"deleted": operation["ids"], "names": names}, None
    if op == "call":
        # classify() already required an active registry row and a valid contract.
        records = _existing(model, operation["ids"])
        _check_unchanged(records, operation.get("expectedWriteDate"))
        returned = getattr(records, operation["method"])(**(operation.get("kwargs") or {}))
        return dict(_json_safe(returned), ids=records.ids), None
    _refuse("unknown operation")

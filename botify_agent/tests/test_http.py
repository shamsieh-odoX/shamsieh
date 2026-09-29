import hashlib
import hmac
import json
import os
import re
import time
from datetime import timedelta
from unittest.mock import patch

from odoo import SUPERUSER_ID, api, fields
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, JsonRpcException, new_test_user, tagged

from ..services import classify, executor, grant

SECRET = "wss_module-test-secret-000000000000000000"
KEY = "wsk_module_test_installation"
MODULE = os.path.dirname(os.path.dirname(__file__))


@tagged("post_install", "-at_install")
class TestBotifyAgentHttp(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        params = cls.env["ir.config_parameter"].sudo()
        for key, value in {
            "enabled": "True",
            "api_url": "https://api.botify.test",
            "installation_key": KEY,
            "secret": SECRET,
            "allow_low_write": "True",
            "allow_high_write": "True",
        }.items():
            params.set_param("botify_agent." + key, value)
        cls.employee = new_test_user(
            cls.env, login="botify_employee", password="botify_employee_pw",
            groups="base.group_user,base.group_partner_manager,botify_agent.group_botify_user",
        )
        cls.outsider = new_test_user(cls.env, login="no_botify", password="no_botify_pw", groups="base.group_user")
        cls.colleague = new_test_user(
            cls.env, login="botify_colleague", groups="base.group_user,botify_agent.group_botify_user"
        )
        cls.partner = cls.env["res.partner"].create({"name": "Azure Interior", "phone": "111"})

    def setUp(self):
        super().setUp()
        self.session = self.authenticate("botify_employee", "botify_employee_pw")

    # -- helpers --------------------------------------------------------------

    def csrf(self):
        secret = self.env["ir.config_parameter"].sudo().get_param("database.secret")
        max_ts = int(time.time() + 3600)
        message = ("%s%s" % (self.session.sid[:42], max_ts)).encode()
        return "%so%s" % (hmac.new(secret.encode("ascii"), message, hashlib.sha1).hexdigest(), max_ts)

    def post(self, route, params=None, headers=None, csrf=True):
        sent = {"X-Botify-CSRF": self.csrf()} if csrf else {}
        sent.update(headers or {})
        return self.make_jsonrpc_request(route, params or {}, headers=sent)

    def grant(self, op, risk_class="low_write", **overrides):
        now = int(time.time())
        payload = {
            "v": 1,
            "iss": KEY,
            "callId": "call-%s:exec" % os.urandom(6).hex(),
            "runId": "run-1",
            "sessionId": "session-1",
            "db": self.env.cr.dbname,
            "uid": self.employee.id,
            "sb": grant.session_binding(SECRET, self.session.sid),
            "riskClass": risk_class,
            "approvalId": None,
            "op": op,
            "iat": now,
            "exp": now + 120,
        }
        payload.update(overrides)
        return payload, grant.sign_grant(SECRET, payload)

    def execute(self, token, context=None):
        return self.post("/botify_agent/v1/execute", {"grant_token": token, **({"context": context} if context else {})})

    def audit(self, call_id):
        """Read from a fresh cursor, after the request finished."""
        with self.registry.cursor() as cr:
            rows = api.Environment(cr, SUPERUSER_ID, {})["botify.agent.operation"].search([("call_id", "=", call_id)])
            return [(row.status, row.error_code, row.user_id.id) for row in rows]

    def write_op(self, values, ids=None):
        return {"op": "write", "model": "res.partner", "ids": ids or [self.partner.id], "values": values}

    # -- CSRF -----------------------------------------------------------------

    def test_every_route_requires_the_csrf_token(self):
        for route in (
            "/botify_agent/v1/identity",
            "/botify_agent/v1/execute",
            "/botify_agent/v1/events/pending",
            "/botify_agent/v1/events/ack",
        ):
            answer = self.post(route, {}, csrf=False)
            self.assertEqual(answer["error"]["code"], "CSRF_FAILED", route)
            answer = self.post(route, {}, headers={"Sec-Fetch-Site": "cross-site"})
            self.assertEqual(answer["error"]["code"], "CSRF_FAILED", route)
            answer = self.post(route, {}, headers={"X-Botify-CSRF": "0" * 40 + "o1"})
            self.assertEqual(answer["error"]["code"], "CSRF_FAILED", route)

    # -- identity -------------------------------------------------------------

    def test_identity_asserts_the_session_user_bound_to_this_session(self):
        answer = self.post("/botify_agent/v1/identity")
        self.assertTrue(answer["ok"], answer)
        token = answer["result"]["assertion"]
        payload = grant._open(grant.derive_key(SECRET, "identity"), "o1", token, 4096)
        self.assertEqual(payload["uid"], self.employee.id)
        self.assertEqual(payload["iss"], KEY)
        self.assertEqual(payload["db"], self.env.cr.dbname)
        self.assertEqual(payload["sb"], grant.session_binding(SECRET, self.session.sid))
        self.assertLessEqual(payload["exp"] - payload["iat"], 120)
        self.assertEqual(answer["result"]["siteKey"], KEY)

    def test_identity_refused_outside_the_group_or_when_disabled(self):
        self.session = self.authenticate("no_botify", "no_botify_pw")
        self.assertEqual(self.post("/botify_agent/v1/identity")["error"]["code"], "ACCESS_DENIED")
        self.env["ir.config_parameter"].sudo().set_param("botify_agent.enabled", "False")
        self.session = self.authenticate("botify_employee", "botify_employee_pw")
        self.assertEqual(self.post("/botify_agent/v1/identity")["error"]["code"], "INTEGRATION_DISABLED")

    # -- grant binding --------------------------------------------------------

    def test_grants_bound_to_another_session_user_or_database_are_refused(self):
        op = self.write_op({"phone": "999"})
        cases = {
            "uid": {"uid": self.outsider.id},
            "db": {"db": "another_db"},
            "sb": {"sb": "B" * 43},
            "iss": {"iss": "wsk_another_installation"},
            "expired": {"iat": int(time.time()) - 300, "exp": int(time.time()) - 10},
        }
        for name, overrides in cases.items():
            payload, token = self.grant(op, **overrides)
            answer = self.execute(token)
            self.assertEqual(answer["error"]["code"], "GRANT_REJECTED", name)
            self.assertEqual(self.audit(payload["callId"]), [], name)
        _payload, token = self.grant(op)
        head, body, mac = token.split(".")
        tampered = grant._b64(json.dumps(dict(_payload, op=self.write_op({"phone": "000"}))).encode())
        self.assertEqual(self.execute("%s.%s.%s" % (head, tampered, mac))["error"]["code"], "GRANT_REJECTED")
        self.assertEqual(self.partner.phone, "111")

    # -- execution and audit ---------------------------------------------------

    def test_success_is_audited_and_a_replay_returns_the_stored_result(self):
        payload, token = self.grant(self.write_op({"phone": "222"}))
        answer = self.execute(token)
        self.assertEqual(answer, {"ok": True, "result": {"ids": [self.partner.id], "updated": 1}})
        self.assertEqual(self.audit(payload["callId"]), [("done", False, self.employee.id)])
        self.partner.invalidate_recordset()
        self.assertEqual(self.partner.phone, "222")
        # Attributed to the employee in Odoo's own tracking too.
        self.assertEqual(self.partner.write_uid, self.employee)

        self.partner.phone = "333"
        replay = self.execute(token)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["result"], answer["result"])
        self.partner.invalidate_recordset()
        self.assertEqual(self.partner.phone, "333", "a replay never executes again")
        self.assertEqual(len(self.audit(payload["callId"])), 1)

    def test_a_failed_operation_rolls_back_but_its_audit_stays(self):
        values = {"name": "Renamed", "parent_id": self.partner.id}  # recursive hierarchy: ValidationError
        payload, token = self.grant(self.write_op(values), risk_class="high_write")
        answer = self.execute(token)
        self.assertEqual(answer["error"]["code"], "VALIDATION_FAILED")
        self.partner.invalidate_recordset()
        self.assertEqual(self.partner.name, "Azure Interior")
        self.assertEqual(self.audit(payload["callId"]), [("failed", "VALIDATION_FAILED", self.employee.id)])

    def test_an_unexpected_failure_is_audited_without_leaking_internals(self):
        payload, token = self.grant(self.write_op({"phone": "444"}))
        with patch.object(executor, "run", side_effect=RuntimeError("secret internals")):
            answer = self.execute(token)
        self.assertEqual(answer["error"]["code"], "INTERNAL")
        self.assertNotIn("secret internals", answer["error"]["message"])
        self.assertEqual(self.audit(payload["callId"]), [("failed", "INTERNAL", self.employee.id)])

    def test_odoo_permissions_decide_not_the_grant(self):
        company = self.env.company
        payload, token = self.grant({"op": "write", "model": "res.company", "ids": [company.id], "values": {"phone": "1"}})
        answer = self.execute(token)
        self.assertEqual(answer["error"]["code"], "ACCESS_DENIED")
        self.assertEqual(self.audit(payload["callId"]), [("failed", "ACCESS_DENIED", self.employee.id)])

    def test_companies_outside_the_employee_are_refused(self):
        other = self.env["res.company"].create({"name": "Other Co"})
        _payload, token = self.grant({"op": "count", "model": "res.partner", "domain": []}, risk_class="read")
        answer = self.execute(token, context={"allowed_company_ids": [other.id]})
        self.assertEqual(answer["error"]["code"], "ACCESS_DENIED")

    # -- classification ----------------------------------------------------------

    def test_odoo_refuses_a_grant_weaker_than_its_own_classification(self):
        # Changing a relation on an existing record is high_write, whatever the grant says.
        other = self.env["res.partner"].create({"name": "Deco Addict"})
        _payload, token = self.grant(self.write_op({"parent_id": other.id}), risk_class="low_write")
        self.assertEqual(self.execute(token)["error"]["code"], "GRANT_REJECTED")
        # A class Odoo has not enabled is refused even with a matching grant.
        _payload, token = self.grant(self.write_op({"active": False}), risk_class="destructive")
        self.assertEqual(self.execute(token)["error"]["code"], "RISK_CLASS_DISABLED")
        # Protected fields are never written generically.
        for field in ("company_id", "create_uid", "commercial_partner_id"):
            _payload, token = self.grant(self.write_op({field: 1}), risk_class="high_write")
            self.assertEqual(self.execute(token)["error"]["code"], "OPERATION_REFUSED", field)

    def test_classification_does_not_depend_on_value_shape_or_key_order(self):
        env = self.env(user=self.employee)
        partner_write = lambda values: {"op": "write", "model": "res.partner", "ids": [self.partner.id], "values": values}  # noqa: E731
        # Odoo stores bool(value): every falsy value archives.
        for value in (False, 0, None, ""):
            self.assertEqual(classify.classify(env, partner_write({"active": value})), "destructive", value)
        # Financial and destructive at once is refused, whatever the key order.
        for values in ({"bank_ids": [[6, 0, []]], "active": False}, {"active": False, "bank_ids": [[6, 0, []]]}):
            with self.assertRaises(classify.Refused) as refused:
                classify.classify(env, partner_write(values))
            self.assertIn("mixed_high_risk", str(refused.exception))
        # Records whose creation sends messages.
        self.assertEqual(
            classify.classify(env, {"op": "create", "model": "mail.message", "values": {"body": "hi"}}),
            "external_communication",
        )

    def test_a_grant_of_another_top_class_is_refused(self):
        # Odoo sees a financial change; a grant saying destructive does not cover it.
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("botify_agent.allow_financial", "True")
        params.set_param("botify_agent.allow_destructive", "True")
        _payload, token = self.grant(self.write_op({"bank_ids": [[6, 0, []]]}), risk_class="destructive")
        self.assertEqual(self.execute(token)["error"]["code"], "GRANT_REJECTED")

    def test_business_methods_need_a_registered_contract(self):
        method = self.env["botify.agent.method"].create(
            {
                "model": "res.partner",
                "method": "message_post",
                "risk_class": "low_write",
                "params_schema": json.dumps(
                    {"type": "object", "properties": {"body": {"type": "string", "maxLength": 200}}, "required": ["body"]}
                ),
            }
        )
        call = {"op": "call", "model": "res.partner", "method": "message_post", "ids": [self.partner.id]}

        def run(kwargs, method_name="message_post"):
            return self.execute(self.grant(dict(call, method=method_name, kwargs=kwargs))[1])

        self.assertEqual(run({"body": "hi", "subtype_xmlid": "mail.mt_comment"})["error"]["code"], "INVALID_ARGUMENTS")
        # A refusal after the grant is verified is audited under its callId, and a replay gets it again.
        payload, token = self.grant(dict(call, kwargs={"body": "hi", "extra": 1}))
        self.assertEqual(self.execute(token)["error"]["code"], "INVALID_ARGUMENTS")
        self.assertEqual(self.audit(payload["callId"]), [("failed", "INVALID_ARGUMENTS", self.employee.id)])
        self.assertTrue(self.execute(token)["replayed"])
        self.assertEqual(run({})["error"]["code"], "INVALID_ARGUMENTS")
        self.assertEqual(run({}, "message_subscribe")["error"]["code"], "METHOD_NOT_ALLOWED")
        self.assertEqual(run({}, "_message_log")["error"]["code"], "METHOD_NOT_ALLOWED")
        self.assertTrue(run({"body": "Called by the agent"})["ok"])
        method.active = False
        self.assertEqual(run({"body": "again"})["error"]["code"], "METHOD_NOT_ALLOWED")

    def test_orm_methods_cannot_be_registered_as_business_actions(self):
        for name in ("write", "unlink", "sudo", "with_user"):
            with self.assertRaises(Exception):
                with self.env.cr.savepoint():
                    self.env["botify.agent.method"].create({"model": "res.partner", "method": name, "risk_class": "high_write"})

    # -- reads, links, discovery -------------------------------------------------

    def test_reads_return_module_generated_links_and_open_record_stays_in_the_browser(self):
        # The link's origin is web.base.url, never the host the request came in on.
        self.env["ir.config_parameter"].sudo().set_param("web.base.url", "https://erp.example.com")
        _payload, token = self.grant(
            {"op": "search", "model": "res.partner", "domain": [["id", "=", self.partner.id]], "fields": ["name"], "limit": 5, "offset": 0},
            risk_class="read",
        )
        record = self.execute(token)["result"]["records"][0]
        self.assertEqual(record["url"], "https://erp.example.com/odoo/res.partner/%d" % self.partner.id)
        _payload, token = self.grant({"op": "open_record", "model": "res.partner", "ids": [self.partner.id]}, risk_class="read")
        answer = self.execute(token)
        self.assertEqual(answer["client"]["action"]["res_id"], self.partner.id)
        self.assertEqual(answer["result"]["url"], "https://erp.example.com/odoo/res.partner/%d" % self.partner.id)
        # No link for a record the employee cannot read: the operation is refused instead.
        _payload, token = self.grant({"op": "open_record", "model": "ir.config_parameter", "ids": [self.env["ir.config_parameter"].sudo().search([], limit=1).id]}, risk_class="read")
        refused = self.execute(token)
        self.assertFalse(refused["ok"])
        self.assertNotIn("url", str(refused))

    def test_discovery_uses_business_model_rights_without_ir_model_access(self):
        # Employees need not belong to the Access Rights group to find a
        # readable model. Client-action names may use hyphens instead of dots.
        _payload, token = self.grant({"op": "list_models", "query": "res-partner", "limit": 10}, risk_class="read")
        models = self.execute(token)["result"]["models"]
        self.assertIn("res.partner", [row["model"] for row in models])
        _payload, token = self.grant({"op": "list_models", "query": "Internal Res-Partner", "limit": 10}, risk_class="read")
        self.assertIn("res.partner", [row["model"] for row in self.execute(token)["result"]["models"]])
        _payload, token = self.grant({"op": "describe_model", "model": "res.partner"}, risk_class="read")
        self.assertEqual(self.execute(token)["result"]["model"], "res.partner")

    def test_describe_marks_protected_fields_readonly_and_lists_allowed_methods(self):
        self.env["botify.agent.field_rule"].create({"model": "res.partner", "field": "comment", "risk_class": "financial"})
        _payload, token = self.grant({"op": "describe_model", "model": "res.partner"}, risk_class="read")
        described = self.execute(token)["result"]
        self.assertTrue(described["fields"]["company_id"]["readonly"])
        self.assertNotIn("readonly", described["fields"]["phone"])
        self.assertEqual(described["fields"]["comment"]["riskClass"], "financial")
        _payload, token = self.grant({"op": "describe_model", "model": "ir.config_parameter"}, risk_class="read")
        self.assertEqual(self.execute(token)["error"]["code"], "ACCESS_DENIED")

    def test_stored_editable_computed_fields_are_writable(self):
        # Odoo persists writes to a stored compute with readonly=False (crm.lead.stage_id,
        # res.partner.company_registry); a non-stored compute without inverse drops them.
        _payload, token = self.grant({"op": "describe_model", "model": "res.partner"}, risk_class="read")
        fields = self.execute(token)["result"]["fields"]
        self.assertNotIn("readonly", fields["company_registry"])
        self.assertTrue(fields["display_name"]["readonly"])
        _payload, token = self.grant(self.write_op({"company_registry": "REG-1"}))
        self.assertTrue(self.execute(token)["ok"])
        self.partner.invalidate_recordset()
        self.assertEqual(self.partner.company_registry, "REG-1")

    # -- code rules ----------------------------------------------------------------

    def test_no_sudo_on_the_execution_path(self):
        for path in ("services/executor.py", "services/classify.py", "services/guard.py", "controllers/main.py"):
            with open(os.path.join(MODULE, path), encoding="utf-8") as handle:
                self.assertIsNone(re.search(r"\.sudo\(", handle.read()), path)

    # -- notification events --------------------------------------------------

    def events_model(self):
        model = self.env["botify.agent.event"]
        self.patch(type(model), "_botify_event_kinds", lambda _self: {"test.happened": {"what": ("str", True), "count": ("int", False)}})
        return model

    def pending(self):
        answer = self.post("/botify_agent/v1/events/pending")
        self.assertTrue(answer["ok"], answer)
        return [
            grant._open(grant.derive_key(SECRET, "notification"), "n1", token, 8192)
            for token in answer["result"]["events"]
        ]

    def ack(self, event, **overrides):
        now = int(time.time())
        payload = {"v": 1, "iss": KEY, "db": self.env.cr.dbname, "uid": event.user_id.id,
                   "eventId": event.event_id, "outcome": "delivered", "iat": now, "exp": now + 300}
        payload.update(overrides)
        return grant._sign(grant.derive_key(SECRET, "ack"), "a1", payload)

    def test_notify_records_only_valid_events_for_botify_users(self):
        events = self.events_model()
        event = events._notify(self.employee, "test.happened", {"what": "leave", "count": 2, "extra": None})
        self.assertTrue(event)
        self.assertEqual(json.loads(event.facts_json), {"count": 2, "what": "leave"})
        self.assertEqual(event.state, "pending")
        refused = {
            "unknown kind": (self.employee, "test.other", {"what": "x"}),
            "unknown fact": (self.employee, "test.happened", {"what": "x", "secret": "y"}),
            "missing fact": (self.employee, "test.happened", {"count": 1}),
            "wrong type": (self.employee, "test.happened", {"what": "x", "count": "2"}),
            "bool is not int": (self.employee, "test.happened", {"what": "x", "count": True}),
            "too long": (self.employee, "test.happened", {"what": "x" * 201}),
            "not a Botify user": (self.outsider, "test.happened", {"what": "x"}),
        }
        for name, (user, kind, facts) in refused.items():
            self.assertFalse(events._notify(user, kind, facts), name)
        self.env["ir.config_parameter"].sudo().set_param("botify_agent.enabled", "False")
        self.assertFalse(events._notify(self.employee, "test.happened", {"what": "x"}), "disabled")
        self.assertEqual(events.sudo().search_count([]), 1)

    def test_notify_is_not_callable_from_the_browser_and_events_are_not_readable(self):
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request(
                "/web/dataset/call_kw/botify.agent.event/_notify",
                {"model": "botify.agent.event", "method": "_notify",
                 "args": [self.employee.id, "test.happened", {"what": "x"}], "kwargs": {}},
            )
        self.assertEqual(self.env["botify.agent.event"].sudo().search_count([]), 0)
        with self.assertRaises(AccessError):
            self.env["botify.agent.event"].with_user(self.employee).search([])

    def test_pending_hands_out_only_the_employees_own_events_signed_and_leased(self):
        events = self.events_model()
        own = events._notify(self.employee, "test.happened", {"what": "mine"}, company=self.env.company)
        self.assertTrue(events._notify(self.colleague, "test.happened", {"what": "not mine"}))
        [payload] = self.pending()
        self.assertEqual(
            {key: payload[key] for key in ("iss", "db", "uid", "eventId", "kind", "facts")},
            {"iss": KEY, "db": self.env.cr.dbname, "uid": self.employee.id, "eventId": own.event_id,
             "kind": "test.happened", "facts": {"what": "mine"}},
        )
        self.assertEqual(payload["company"]["id"], self.env.company.id)
        self.assertLessEqual(payload["exp"] - payload["iat"], 300)
        self.assertEqual(self.pending(), [], "leased: a second tab gets nothing")
        self.assertEqual((own.state, own.attempts), ("delivering", 1))
        # Nobody acknowledged it (Botify down): handed out again once the lease is over.
        own.sudo().lease_until = fields.Datetime.now() - timedelta(seconds=1)
        self.assertEqual([payload["eventId"] for payload in self.pending()], [own.event_id])
        self.assertEqual(own.attempts, 2)

    def test_pending_is_refused_outside_the_group_or_when_disabled(self):
        self.session = self.authenticate("no_botify", "no_botify_pw")
        self.assertEqual(self.post("/botify_agent/v1/events/pending")["error"]["code"], "ACCESS_DENIED")
        self.env["ir.config_parameter"].sudo().set_param("botify_agent.enabled", "False")
        self.session = self.authenticate("botify_employee", "botify_employee_pw")
        self.assertEqual(self.post("/botify_agent/v1/events/pending")["error"]["code"], "INTEGRATION_DISABLED")

    def test_only_a_valid_ack_for_the_employees_own_event_changes_it(self):
        events = self.events_model()
        own = events._notify(self.employee, "test.happened", {"what": "mine"})
        other = events._notify(self.colleague, "test.happened", {"what": "not mine"})
        forged = self.ack(own).rsplit(".", 1)[0] + "." + grant._b64(b"x" * 32)
        wrong_purpose = grant._sign(grant.derive_key(SECRET, "grant"), "a1", {"eventId": own.event_id})
        refused = [
            forged,
            wrong_purpose,
            self.ack(own, iss="wsk_another_installation"),
            self.ack(own, db="another_db"),
            self.ack(own, uid=self.outsider.id),
            self.ack(own, iat=int(time.time()) - 400, exp=int(time.time()) - 100),
            self.ack(other),
            self.ack(other, uid=self.employee.id),
        ]
        answer = self.post("/botify_agent/v1/events/ack", {"acks": refused})
        self.assertEqual(answer["result"]["acknowledged"], 0, answer)
        self.assertEqual((own.state, other.state), ("pending", "pending"))
        answer = self.post("/botify_agent/v1/events/ack", {"acks": [self.ack(own)]})
        self.assertEqual(answer["result"]["acknowledged"], 1)
        replayed = self.post("/botify_agent/v1/events/ack", {"acks": [self.ack(own)]})
        self.assertEqual(replayed["result"]["acknowledged"], 0)
        self.assertEqual(own.state, "delivered")
        self.assertTrue(own.delivered_at)
        # A late "rejected" receipt never undoes a delivery.
        self.post("/botify_agent/v1/events/ack", {"acks": [self.ack(own, outcome="rejected")]})
        self.assertEqual(own.state, "delivered")

    def test_a_rejected_event_fails_and_is_never_handed_out_again(self):
        events = self.events_model()
        event = events._notify(self.employee, "test.happened", {"what": "x"})
        self.post("/botify_agent/v1/events/ack", {"acks": [self.ack(event, outcome="rejected", reason="unknown kind")]})
        self.assertEqual((event.state, event.last_error), ("failed", "unknown kind"))
        self.assertEqual(self.pending(), [])

    def test_undelivered_events_back_off_and_expire_after_a_week(self):
        events = self.events_model()
        event = events._notify(self.employee, "test.happened", {"what": "waiting"})
        leases = []
        for _attempt in range(8):
            event.sudo().lease_until = fields.Datetime.now() - timedelta(seconds=1)
            self.assertEqual(len(self.pending()), 1)
            leases.append(round((event.lease_until - fields.Datetime.now()).total_seconds() / 60))
        # 1, 2, 4 … minutes, capped at an hour; still deliverable after many tries.
        self.assertEqual(leases, [1, 2, 4, 8, 16, 32, 60, 60])
        self.assertEqual((event.state, event.attempts), ("delivering", 8))
        self.env.cr.execute(
            "UPDATE botify_agent_event SET create_date = %s WHERE id = %s",
            (fields.Datetime.now() - timedelta(days=8), event.id),
        )
        events.invalidate_model()
        events._gc()
        self.assertEqual(event.state, "expired")
        event.sudo().lease_until = False
        self.assertEqual(self.pending(), [])

    def test_labels_are_measured_as_botify_measures_them(self):
        events = self.events_model()
        self.assertTrue(events._notify(self.employee, "test.happened", {"what": "🌴" * 100}))
        self.assertFalse(events._notify(self.employee, "test.happened", {"what": "🌴" * 101}))

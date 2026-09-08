"""End-to-end grant + RPC tests against the real HTTP endpoints.

Exercises the full odoo-enterprise-rebuild flow: identity() mints a
delegation -> grant() proves possession of it and returns a signed,
single-use, operation-bound grant -> rpc() verifies the grant, recomputes its
operation hash from the actual body, atomically consumes its jti, and only
THEN executes with_user(uid). Covers the AC-27 security matrix items that are
addon-local: identity/grant forgery, replay, operation-mismatch tampering,
cross-scope company escalation, portal/inactive/superuser rejection,
unclassified-model and forbidden-field policy denial, and batch-size limits.

Verified against a real, containerized Odoo 18 + Postgres 16 (addon
mounted read-only) — see docs/odoo/runbook.md "Sandbox verification limits"
and docs/odoo/final-report.md for the exact command and results (3
consecutive clean runs, 0 failed/0 error(s) of 47 tests). To re-run
yourself:

    odoo -d <db> -i botify_agent --test-enable --stop-after-init \
         --test-tags /botify_agent
"""

import json
import time

from odoo import fields
from odoo.tests import common, tagged
from odoo.tools import mute_logger

from ..models import botify_security

SECRET = "test-secret-value-do-not-use-in-production"
AGENT_ID = "agent-uuid"
INSTALLATION_ID = "connection-uuid"


@tagged("post_install", "-at_install", "botify_agent")
class TestGrantAndRpcFlow(common.HttpCase):
    def setUp(self):
        super().setUp()
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("botify_agent.enabled", "True")
        params.set_param("botify_agent.base_url", "https://api.example.test")
        params.set_param("botify_agent.agent_id", AGENT_ID)
        params.set_param("botify_agent.installation_id", INSTALLATION_ID)
        params.set_param("botify_agent.shared_secret", SECRET)
        params.set_param("botify_agent.assertion_ttl", "120")
        params.set_param("botify_agent.grant_ttl", "90")

        from ._helpers import user_group_field

        self.employee = self.env["res.users"].create({
            "name": "Grant Flow Employee",
            "login": "botify.grantflow@example.com",
            user_group_field(self.env): [(6, 0, [self.env.ref("base.group_user").id])],
        })
        self.partner = self.env["res.partner"].create({"name": "Grant Flow Customer"})

    # -- helpers --------------------------------------------------------

    def _mint_delegation(self):
        self.authenticate("botify.grantflow@example.com", "botify.grantflow@example.com")
        response = self.url_open(
            "/botify_agent/identity",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {}}),
            headers={"Content-Type": "application/json"},
        )
        result = response.json()["result"]
        self.assertIn("delegation_id", result)
        self.assertIn("delegation_key", result)
        return result

    def _signed_post(self, path, body_dict, delegation_key=None):
        body = json.dumps(body_dict).encode()
        ts = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "X-Botify-Timestamp": ts,
            "X-Botify-Signature": "sha256=" + botify_security.sign_request(SECRET, ts, body),
        }
        if delegation_key:
            headers["X-Botify-Delegation-Proof"] = "sha256=" + botify_security.hmac_hex(
                delegation_key, "{}.{}".format(ts, body.decode("utf-8"))
            )
        return self.url_open(path, data=body, headers=headers)

    def _request_grant(self, delegation, model, method, **kwargs):
        payload = {
            "installation_id": INSTALLATION_ID,
            "delegation_id": delegation["delegation_id"],
            "model": model,
            "method": method,
        }
        payload.update(kwargs)
        return self._signed_post("/botify_agent/grant", payload, delegation["delegation_key"])

    def _rpc(self, grant_token, model, method, **kwargs):
        payload = {"installation_id": INSTALLATION_ID, "model": model, "method": method}
        payload.update(kwargs)
        body = json.dumps(payload).encode()
        ts = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "X-Botify-Timestamp": ts,
            "X-Botify-Signature": "sha256=" + botify_security.sign_request(SECRET, ts, body),
            "X-Botify-Grant": grant_token,
        }
        return self.url_open("/botify_agent/rpc", data=body, headers=headers)

    # -- happy path -------------------------------------------------------

    def test_full_flow_read(self):
        delegation = self._mint_delegation()
        # domain lives INSIDE kwargs for search-family calls, exactly as the
        # real backend client sends it (odooAddonClient.ts / grant.ts never
        # populate a top-level `domain` field — see botify_canonical.py's
        # module docstring). A prior version of this test sent domain as a
        # top-level sibling of kwargs, which main.py correctly ignores for
        # the actual ORM call (it only ever reads domain from inside
        # kwargs_in) — caught by a real Odoo 18 run returning an unfiltered
        # result instead of failing the request; see docs/odoo/final-report.md.
        search_kwargs = {"fields": ["name"], "domain": [["id", "=", self.partner.id]]}
        grant_resp = self._request_grant(
            delegation, "res.partner", "search_read", ids=[], kwargs=search_kwargs,
        )
        grant = grant_resp.json()
        self.assertIn("grant", grant)
        self.assertEqual(grant["op_class"], "read")

        rpc_resp = self._rpc(
            grant["grant"], "res.partner", "search_read", ids=[], kwargs=search_kwargs,
        )
        result = rpc_resp.json()
        self.assertIn("result", result, result)
        self.assertEqual(result["result"][0]["name"], "Grant Flow Customer")

    # -- replay -------------------------------------------------------------

    # The replay IS the assertion; its UNIQUE violation is expected noise.
    @mute_logger("odoo.sql_db", "odoo.addons.botify_agent.controllers.main")
    def test_grant_cannot_be_replayed(self):
        delegation = self._mint_delegation()
        grant = self._request_grant(
            delegation, "res.partner", "search_read", ids=[], kwargs={"fields": ["name"]}
        ).json()["grant"]
        first = self._rpc(grant, "res.partner", "search_read", ids=[], kwargs={"fields": ["name"]})
        self.assertIn("result", first.json())
        second = self._rpc(grant, "res.partner", "search_read", ids=[], kwargs={"fields": ["name"]})
        self.assertEqual(second.json()["error"]["name"], "grant_replayed")

    # -- operation mismatch (tamper) ----------------------------------------

    @mute_logger("odoo.addons.botify_agent.controllers.main")
    def test_tampering_the_operation_after_grant_is_rejected(self):
        delegation = self._mint_delegation()
        grant = self._request_grant(
            delegation, "res.partner", "write", ids=[self.partner.id], kwargs={"vals": {"name": "Approved Name"}},
        ).json()["grant"]
        tampered = self._rpc(
            grant, "res.partner", "write", ids=[self.partner.id], kwargs={"vals": {"name": "DIFFERENT NAME"}}
        )
        self.assertEqual(tampered.json()["error"]["name"], "grant_operation_mismatch")

    # -- cross-scope / privilege checks --------------------------------------

    def test_grant_rejects_company_outside_delegation_scope(self):
        other_company = self.env["res.company"].create({"name": "Outside Co"})
        delegation = self._mint_delegation()
        resp = self._request_grant(
            delegation, "res.partner", "search_read",
            ids=[], kwargs={}, allowed_company_ids=[other_company.id],
        )
        self.assertEqual(resp.json()["error"]["name"], "company_out_of_scope")

    def test_grant_rejects_reserved_model(self):
        # 2026-09 policy change: a model with no manifest entry defaults OPEN
        # unless it is in Odoo's reserved/infra namespace. ir.config_parameter
        # is reserved, so it stays hard-blocked regardless.
        delegation = self._mint_delegation()
        resp = self._request_grant(delegation, "ir.config_parameter", "search_read", ids=[], kwargs={})
        self.assertEqual(resp.json()["error"]["name"], "model_reserved")

    def test_grant_rejects_forbidden_field(self):
        delegation = self._mint_delegation()
        resp = self._request_grant(
            delegation, "res.partner", "write", ids=[self.partner.id], kwargs={"vals": {"password": "x"}}
        )
        self.assertEqual(resp.json()["error"]["name"], "field_denied")

    def test_grant_rejects_when_delegation_revoked(self):
        delegation = self._mint_delegation()
        rec = self.env["botify.agent.delegation"].sudo().browse(int(delegation["delegation_id"]))
        rec.write({"revoked_at": fields.Datetime.now()})
        resp = self._request_grant(delegation, "res.partner", "search_read", ids=[], kwargs={})
        self.assertEqual(resp.json()["error"]["name"], "delegation_revoked")

    def test_grant_rejects_batch_too_large(self):
        delegation = self._mint_delegation()
        ids = list(range(1, 200))
        resp = self._request_grant(
            delegation, "res.partner", "write", ids=ids, kwargs={"vals": {"name": "x"}}, is_batch=True
        )
        self.assertEqual(resp.json()["error"]["name"], "batch_too_large")

    # -- installation / audience binding -------------------------------------

    def test_rpc_rejects_grant_for_wrong_installation(self):
        # Mint a grant, then flip the installation_id config so the grant's
        # `bi` claim no longer matches — simulates presenting a grant minted
        # by one connection's Botify install against a different one.
        delegation = self._mint_delegation()
        grant = self._request_grant(
            delegation, "res.partner", "search_read", ids=[], kwargs={}
        ).json()["grant"]
        self.env["ir.config_parameter"].sudo().set_param("botify_agent.installation_id", "a-different-connection")
        resp = self._rpc(grant, "res.partner", "search_read", ids=[], kwargs={})
        self.assertIn(resp.json()["error"]["name"], ("installation_mismatch", "audience_mismatch"))


if __name__ == "__main__":
    common.unittest.main()



@tagged("post_install", "-at_install", "botify_agent")
class TestCustomModelPolicyGate(common.HttpCase):
    """The Odoo-side half of the custom-model classification decision.

    2026-09 policy change: a model with no global manifest entry and no
    per-tenant classification now defaults OPEN (classification_source ==
    "default") as long as it is not in Odoo's reserved/infra namespace — this
    includes a tenant's own custom/Studio models, so `x_botify_test_note` is
    reachable with or without a Botify-supplied classification and with or
    without `botify_agent.allow_custom_models` on. That switch no longer gates
    reachability; it only gates whether Botify's own RICHER classification for
    a specific custom model (its declared write operation class, and a
    sensitivity flag used for audit logging) is honored instead of the
    generic default entry. It still cannot be set from Botify, so a
    compromised Botify cannot make its own classification authoritative on
    its own.

    `x_botify_test_note` is a real Studio-style manual model, so this exercises
    the genuine dot-less `x_` shape end to end rather than asserting against a
    name that does not exist. It is created in setUpClass, not setUp: creating
    a manual model performs DDL and reflection that a per-test rollback does
    not fully undo, so a per-test create collides on ir_model_fields' unique
    constraint from the second test onwards.
    """

    TENANT_ENTRY = {
        "model": "x_botify_test_note",
        "opClasses": ["read", "normal_write"],
        "createOpClass": "normal_write",
        "writeOpClass": "normal_write",
        "sensitive": False,
    }

    # createOpClass deliberately differs from _DEFAULT_MODEL_ENTRY's
    # "normal_write" so a grant's returned op_class can prove whether this
    # classification was actually consulted, rather than the generic default
    # entry that applies to every unclassified model regardless of consent.
    DISTINCT_TENANT_ENTRY = {
        "model": "x_botify_test_note",
        "opClasses": ["read", "capture_write"],
        "createOpClass": "capture_write",
        "writeOpClass": "capture_write",
        "sensitive": False,
    }

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from ._helpers import user_group_field

        cls.employee = cls.env["res.users"].create({
            "name": "Custom Model Employee",
            "login": "botify.custommodel@example.com",
            user_group_field(cls.env): [(6, 0, [cls.env.ref("base.group_user").id])],
        })

        # Odoo creates the `x_name` display-name field automatically for a
        # manual model, so declaring it here would collide on
        # ir_model_fields' UNIQUE(model, name).
        custom_model = cls.env["ir.model"].create({
            "name": "Botify Test Note",
            "model": "x_botify_test_note",
            "state": "manual",
        })
        cls.env["ir.model.access"].create({
            "name": "x_botify_test_note all",
            "model_id": custom_model.id,
            "group_id": cls.env.ref("base.group_user").id,
            "perm_read": True,
            "perm_write": True,
            "perm_create": True,
            "perm_unlink": True,
        })

    def setUp(self):
        super().setUp()
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("botify_agent.enabled", "True")
        params.set_param("botify_agent.base_url", "https://api.example.test")
        params.set_param("botify_agent.agent_id", AGENT_ID)
        params.set_param("botify_agent.installation_id", INSTALLATION_ID)
        params.set_param("botify_agent.shared_secret", SECRET)
        params.set_param("botify_agent.grant_ttl", "90")
        params.set_param("botify_agent.allow_custom_models", "False")

    # Reuse the signing/minting helpers from the flow test above.
    _signed_post = TestGrantAndRpcFlow._signed_post
    _request_grant = TestGrantAndRpcFlow._request_grant
    _rpc = TestGrantAndRpcFlow._rpc

    def _mint_delegation(self):
        self.authenticate("botify.custommodel@example.com", "botify.custommodel@example.com")
        resp = self.url_open(
            "/botify_agent/identity",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {}}),
            headers={"Content-Type": "application/json"},
        )
        return resp.json()["result"]

    def _allow_custom_models(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "botify_agent.allow_custom_models", "True"
        )

    def test_custom_model_write_allowed_without_classification_or_switch(self):
        """No classification sent, switch off -> default-open still applies.

        x_botify_test_note has no global manifest entry and (with no
        classification sent) no tenant entry either, so it falls to
        _DEFAULT_MODEL_ENTRY exactly like any other unclassified model —
        `botify_agent.allow_custom_models` being off does not change that.
        """
        delegation = self._mint_delegation()
        grant_resp = self._request_grant(
            delegation, "x_botify_test_note", "create", kwargs={"vals_list": [{"x_name": "n"}]}
        )
        self.assertEqual(grant_resp.status_code, 200, grant_resp.text)
        self.assertEqual(grant_resp.json()["op_class"], "normal_write")

    def test_custom_model_classification_honored_only_when_switch_is_on(self):
        """The switch's actual job now: whether Botify's own classification
        for this custom model overrides the generic default entry.

        Same classification (createOpClass="capture_write", distinct from the
        default entry's "normal_write") sent both times; only the Odoo-side
        switch differs. Off -> ignored, model falls to the default entry and
        the grant is issued for "normal_write". On -> honored, the grant is
        issued for the classification's own "capture_write" instead. Either
        way the write is reachable — this switch was never what stood between
        it and denial once a model is unclassified.
        """
        delegation = self._mint_delegation()
        off_resp = self._request_grant(
            delegation,
            "x_botify_test_note",
            "create",
            kwargs={"vals_list": [{"x_name": "n"}]},
            tenant_model=self.DISTINCT_TENANT_ENTRY,
        )
        self.assertEqual(off_resp.status_code, 200, off_resp.text)
        self.assertEqual(off_resp.json()["op_class"], "normal_write")

        self._allow_custom_models()
        on_resp = self._request_grant(
            delegation,
            "x_botify_test_note",
            "create",
            kwargs={"vals_list": [{"x_name": "n"}]},
            tenant_model=self.DISTINCT_TENANT_ENTRY,
        )
        self.assertEqual(on_resp.status_code, 200, on_resp.text)
        self.assertEqual(on_resp.json()["op_class"], "capture_write")

    def test_custom_model_write_allowed_when_classified_and_consented(self):
        self._allow_custom_models()
        delegation = self._mint_delegation()
        grant_resp = self._request_grant(
            delegation,
            "x_botify_test_note",
            "create",
            kwargs={"vals_list": [{"x_name": "Written by the assistant"}]},
            tenant_model=self.TENANT_ENTRY,
        )
        self.assertEqual(grant_resp.status_code, 200, grant_resp.text)
        grant = grant_resp.json()
        self.assertEqual(grant["op_class"], "normal_write")

        rpc_resp = self._rpc(
            grant["grant"],
            "x_botify_test_note",
            "create",
            kwargs={"vals_list": [{"x_name": "Written by the assistant"}]},
        )
        result = rpc_resp.json()
        self.assertIn("result", result, result)
        created = self.env["x_botify_test_note"].browse(result["result"])
        self.assertEqual(created.x_name, "Written by the assistant")

    def test_classification_cannot_reclassify_a_standard_model(self):
        """Global manifest supremacy at the authoritative enforcement point.

        A hostile classification claiming res.users is a freely-writable custom
        model must be inert even with the Odoo-side switch on: res.users is in
        Odoo's reserved/infra namespace (sanitize_tenant_model refuses to
        classify it, so evaluate() falls through to is_reserved_model), and
        stays hard-blocked regardless of any classification or grant.
        """
        self._allow_custom_models()
        delegation = self._mint_delegation()
        resp = self._request_grant(
            delegation,
            "res.users",
            "write",
            ids=[self.employee.id],
            kwargs={"vals": {"name": "escalated"}},
            tenant_model={
                "model": "res.users",
                "opClasses": ["read", "normal_write"],
                "createOpClass": "normal_write",
                "writeOpClass": "normal_write",
                "sensitive": False,
            },
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["name"], "model_reserved")


@tagged("post_install", "-at_install", "botify_agent")
class TestMonetaryWriteFlushesAsActingUser(common.HttpCase):
    """Regression: a Monetary write through /rpc must actually reach the DB.

    Odoo 19 pins ``transaction.default_env`` to the ``uid=None`` environment of
    an ``auth="none"`` route (``ir_http._auth_method_none``), and
    ``Transaction.flush()`` uses that env unconditionally. Flushing a dirty
    Monetary field there makes ``fields_numeric.convert_to_column_insert``
    lazily fetch ``res.currency.rounding`` under an env whose ``env.user`` is an
    EMPTY ``res.users()`` recordset, and ``_get_group_ids()`` dies in
    ``ensure_one()``.

    The failure mode is nasty and is what this test pins: /rpc returned 200 with
    a record id, and only THEN did the end-of-request flush blow up and roll the
    transaction back — so the assistant reported success and nothing was
    written. Asserting the response is not enough; the record must exist
    afterwards with the Monetary value it was created with.

    main.py fixes this by calling ``target.env.flush_all()`` (the with_user env)
    inside the RPC handler.

    NOT RUNNABLE without a Monetary-bearing model: the addon only depends on
    base/base_setup/web, so this skips unless crm is installed. On the live
    tenant (where the original traceback came from, crm.lead.create) it runs.
    NEEDS A REAL ODOO 19 RUN TO CONFIRM — it cannot be exercised by the
    stdlib-only test_pure_*.py suite.
    """

    def setUp(self):
        super().setUp()
        if "crm.lead" not in self.env:
            self.skipTest("crm is not installed; no Monetary model to exercise")

        params = self.env["ir.config_parameter"].sudo()
        params.set_param("botify_agent.enabled", "True")
        params.set_param("botify_agent.base_url", "https://api.example.test")
        params.set_param("botify_agent.agent_id", AGENT_ID)
        params.set_param("botify_agent.installation_id", INSTALLATION_ID)
        params.set_param("botify_agent.shared_secret", SECRET)
        params.set_param("botify_agent.assertion_ttl", "120")
        params.set_param("botify_agent.grant_ttl", "90")

        from ._helpers import user_group_field

        groups = [self.env.ref("base.group_user").id]
        salesman = self.env.ref("sales_team.group_sale_salesman", raise_if_not_found=False)
        if salesman:
            groups.append(salesman.id)
        self.employee = self.env["res.users"].create({
            "name": "Monetary Flush Employee",
            "login": "botify.monetary@example.com",
            user_group_field(self.env): [(6, 0, groups)],
        })

    # Reuse the signing/minting helpers from the flow test above.
    _signed_post = TestGrantAndRpcFlow._signed_post
    _request_grant = TestGrantAndRpcFlow._request_grant
    _rpc = TestGrantAndRpcFlow._rpc

    def _mint_delegation(self):
        self.authenticate("botify.monetary@example.com", "botify.monetary@example.com")
        resp = self.url_open(
            "/botify_agent/identity",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {}}),
            headers={"Content-Type": "application/json"},
        )
        return resp.json()["result"]

    def test_monetary_create_survives_end_of_request_flush(self):
        # The exact production sequence: /rpc's own sudo() nonce consumption,
        # then with_user(employee), then a create() that dirties a Monetary
        # field (crm.lead.expected_revenue) which only gets written at flush.
        vals = {"name": "Botify Monetary Lead", "expected_revenue": 1234.5}
        delegation = self._mint_delegation()
        grant_resp = self._request_grant(
            delegation, "crm.lead", "create", ids=[], kwargs={"vals_list": [vals]}
        )
        self.assertEqual(grant_resp.status_code, 200, grant_resp.text)
        grant = grant_resp.json()["grant"]

        rpc_resp = self._rpc(grant, "crm.lead", "create", ids=[], kwargs={"vals_list": [vals]})
        result = rpc_resp.json()
        self.assertIn("result", result, result)
        lead_ids = result["result"]
        self.assertTrue(lead_ids)

        # The whole point: before the fix this passed everything above and the
        # record was gone, because the flush that would have written it raised
        # "Expected singleton: res.users()" after the response was sent.
        self.env.invalidate_all()
        lead = self.env["crm.lead"].sudo().browse(lead_ids)
        self.assertTrue(lead.exists(), "Monetary create was rolled back after a 200 response")
        self.assertEqual(lead.name, "Botify Monetary Lead")
        self.assertEqual(lead.expected_revenue, 1234.5)

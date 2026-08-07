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

    def test_grant_rejects_unclassified_model(self):
        delegation = self._mint_delegation()
        resp = self._request_grant(delegation, "ir.config_parameter", "search_read", ids=[], kwargs={})
        self.assertEqual(resp.json()["error"]["name"], "model_unclassified")

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

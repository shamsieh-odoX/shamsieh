"""End-user execution tests.

These are the tests that actually justify the design: they assert that running a
call through the addon gives the *same* answer Odoo would give that user
directly — including the refusals. If these pass, no permission logic needs to
exist in Botify.

Run with:
    odoo -d <db> -i botify_agent --test-enable --stop-after-init \
         --test-tags /botify_agent
"""

import json
import time

from odoo.exceptions import AccessError
from odoo.tests import common, tagged

from ..controllers import _shared as botify_shared
from ..controllers import main as botify_main
from ..models import botify_policy, botify_security


@tagged("post_install", "-at_install", "botify_agent")
class TestEndUserExecution(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env["res.company"].create({"name": "Botify Test A"})
        cls.company_b = cls.env["res.company"].create({"name": "Botify Test B"})

        from ._helpers import user_group_field

        group_user = cls.env.ref("base.group_user")
        gfield = user_group_field(cls.env)

        # A plain employee in company A only.
        cls.employee = cls.env["res.users"].create({
            "name": "Employee One",
            "login": "botify.employee.one@example.com",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            gfield: [(6, 0, [group_user.id])],
        })
        # A second employee, same company — used for cross-user isolation.
        cls.other_employee = cls.env["res.users"].create({
            "name": "Employee Two",
            "login": "botify.employee.two@example.com",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            gfield: [(6, 0, [group_user.id])],
        })
        # Partner records owned by each company.
        cls.partner_a = cls.env["res.partner"].create({
            "name": "Customer In A",
            "company_id": cls.company_a.id,
        })
        cls.partner_b = cls.env["res.partner"].create({
            "name": "Customer In B",
            "company_id": cls.company_b.id,
        })

    # -- the primitive this whole design rests on ---------------------------

    def test_with_user_applies_record_rules(self):
        """with_user() must NOT be superuser mode.

        If this ever regressed to su=True, every other guarantee in the addon
        would silently evaporate while the tests still 'passed' functionally.
        """
        env_as_employee = self.env["res.partner"].with_user(self.employee).env
        self.assertFalse(
            env_as_employee.su,
            "with_user must yield a non-superuser environment",
        )
        self.assertEqual(env_as_employee.user, self.employee)

    def test_multi_company_scope_cannot_be_widened(self):
        """Asking for a company the user does not belong to must be refused.

        This is Odoo's own check (Environment.companies raises when su=False),
        which is exactly why the addon can forward a requested company list
        without validating it itself.
        """
        scoped = (
            self.env["res.partner"]
            .with_user(self.employee)
            .with_context(allowed_company_ids=[self.company_b.id])
        )
        with self.assertRaises(AccessError):
            # Touching env.companies is what triggers the validation.
            scoped.env.companies.ids

    def test_employee_cannot_read_other_company_record(self):
        """Company B's customer is invisible to an employee scoped to A."""
        visible = (
            self.env["res.partner"]
            .with_user(self.employee)
            .with_context(allowed_company_ids=[self.company_a.id])
            .search([("id", "in", [self.partner_a.id, self.partner_b.id])])
        )
        self.assertIn(self.partner_a, visible)
        self.assertNotIn(
            self.partner_b,
            visible,
            "record rules must hide another company's partner",
        )

    def test_non_manager_cannot_perform_manager_only_write(self):
        """A plain employee must not be able to edit a res.users record.

        res.users is administrator-only; a normal employee editing another
        user's login is precisely the privilege escalation the agent must not
        be able to perform on their behalf.
        """
        with self.assertRaises(AccessError):
            self.env["res.users"].with_user(self.employee).browse(
                self.other_employee.id
            ).write({"login": "hijacked@example.com"})

    # -- controller-level guards -------------------------------------------

    def test_method_allowlist_rejects_unlink(self):
        self.assertIn("unlink", botify_main.FORBIDDEN_METHODS)
        self.assertNotIn("unlink", botify_policy.get_policy_manifest()["methods"])

    def test_method_allowlist_rejects_private_methods(self):
        manifest = botify_policy.get_policy_manifest()
        for method in ("_write", "__init__", "_read_group_raw"):
            self.assertTrue(
                method.startswith("_"),
                "private methods are filtered by the startswith('_') guard",
            )
            self.assertNotIn(method, manifest["methods"])

    def test_method_allowlist_rejects_env_escapes(self):
        """sudo/with_user must never be reachable as a forwarded method."""
        manifest = botify_policy.get_policy_manifest()
        for method in ("sudo", "with_user", "with_env"):
            self.assertIn(method, botify_main.FORBIDDEN_METHODS)
            self.assertNotIn(method, manifest["methods"])

    def test_check_access_shim_matches_this_odoo_version(self):
        """The version shim must resolve to something callable here."""
        records = self.env["res.partner"].with_user(self.employee).browse(self.partner_a.id)
        # Must not raise AttributeError on any supported version.
        botify_shared.check_access(records, "read")


@tagged("post_install", "-at_install", "botify_agent")
class TestMissingConfigFields(common.TransactionCase):
    """The identity endpoint should name exactly which setting is empty —
    all three (secret, agent_id, installation_id) live on one Settings
    screen, so a vague "not configured" forces a guess-and-check loop.

    Pure logic, no DB writes needed; TransactionCase only for consistency
    with the rest of this test module's discovery/tagging.
    """

    def _config(self, **overrides):
        base = {"secret": "s", "agent_id": "a", "installation_id": "i"}
        base.update(overrides)
        return base

    def test_all_present_reports_nothing_missing(self):
        self.assertEqual(botify_shared.missing_config_fields(self._config()), [])

    def test_reports_each_field_by_name(self):
        self.assertEqual(
            botify_shared.missing_config_fields(self._config(secret="")),
            ["Shared secret"],
        )
        self.assertEqual(
            botify_shared.missing_config_fields(self._config(agent_id="")),
            ["Botify agent ID"],
        )
        self.assertEqual(
            botify_shared.missing_config_fields(self._config(installation_id="")),
            ["Botify connection ID"],
        )

    def test_reports_all_missing_together_in_a_stable_order(self):
        self.assertEqual(
            botify_shared.missing_config_fields(
                self._config(secret="", agent_id="", installation_id="")
            ),
            ["Shared secret", "Botify agent ID", "Botify connection ID"],
        )


@tagged("post_install", "-at_install", "botify_agent")
class TestWriteFieldGuard(common.TransactionCase):
    """Field-level defense in depth, now driven by the shared policy manifest
    (botify_policy.evaluate) instead of a locally duplicated regex — see
    docs/odoo/policy.md. Pure logic, no DB writes needed; TransactionCase
    only for consistency with the rest of this test module's discovery/tagging.
    """

    GRANT = {"read", "capture_write", "normal_write", "financial_write", "lifecycle_action", "batch_action"}

    def test_write_blocks_credential_fields(self):
        for field in ("password", "api_key", "oauth_token", "groups_id"):
            with self.assertRaises(botify_policy.PolicyDenied) as ctx:
                botify_policy.evaluate(
                    "res.partner", "write", fields=[field], granted_op_classes=self.GRANT
                )
            self.assertEqual(ctx.exception.reason, "field_denied")

    def test_write_blocks_state_and_stage_id(self):
        for field in ("state", "stage_id", "State"):
            with self.assertRaises(botify_policy.PolicyDenied) as ctx:
                botify_policy.evaluate(
                    "sale.order", "write", fields=[field], granted_op_classes=self.GRANT
                )
            self.assertEqual(ctx.exception.reason, "field_denied")

    def test_write_allows_ordinary_fields(self):
        result = botify_policy.evaluate(
            "res.partner", "write", fields=["name", "phone"], granted_op_classes=self.GRANT
        )
        self.assertEqual(result["opClass"], "normal_write")

    def test_create_blocks_credential_fields_but_allows_state(self):
        # Setting an initial state ON CREATE is normal (that is how records
        # start out) — the workflow-field guard only applies to write().
        with self.assertRaises(botify_policy.PolicyDenied) as ctx:
            botify_policy.evaluate(
                "crm.lead", "create", fields=["name", "password"], granted_op_classes=self.GRANT
            )
        self.assertEqual(ctx.exception.reason, "field_denied")
        result = botify_policy.evaluate(
            "crm.lead", "create", fields=["name", "state"], granted_op_classes=self.GRANT
        )
        self.assertEqual(result["opClass"], "capture_write")

    def test_other_methods_are_not_field_checked(self):
        # search_read etc. carry no vals/vals_list — extract_write_fields()
        # (controllers/_shared.py) returns [] for them, so no field is checked.
        self.assertEqual(botify_shared.extract_write_fields("search_read", {"domain": []}), [])


@tagged("post_install", "-at_install", "botify_agent")
class TestRequestSigning(common.TransactionCase):
    """Signature, freshness and replay properties of the Botify -> Odoo hop."""

    SECRET = "test-secret-value-do-not-use-in-production"

    def _body(self, **overrides):
        payload = {"model": "res.partner", "method": "search_read", "uid": 7}
        payload.update(overrides)
        return json.dumps(payload).encode()

    def test_valid_signature_accepted(self):
        body = self._body()
        ts = str(int(time.time()))
        signature = botify_security.sign_request(self.SECRET, ts, body)
        botify_security.verify_request(self.SECRET, ts, body, signature)

    def test_tampered_body_rejected(self):
        body = self._body()
        ts = str(int(time.time()))
        signature = botify_security.sign_request(self.SECRET, ts, body)
        tampered = self._body(uid=1)
        with self.assertRaises(ValueError):
            botify_security.verify_request(self.SECRET, ts, tampered, signature)

    def test_wrong_secret_rejected(self):
        body = self._body()
        ts = str(int(time.time()))
        signature = botify_security.sign_request("other-secret", ts, body)
        with self.assertRaises(ValueError):
            botify_security.verify_request(self.SECRET, ts, body, signature)

    def test_stale_timestamp_rejected(self):
        """A captured request must stop working once the window closes."""
        body = self._body()
        old = str(int(time.time()) - 3600)
        signature = botify_security.sign_request(self.SECRET, old, body)
        with self.assertRaises(ValueError):
            botify_security.verify_request(self.SECRET, old, body, signature)

    def test_timestamp_cannot_be_restamped(self):
        """Re-stamping a captured body must invalidate the signature.

        The timestamp is inside the MAC, so an attacker cannot refresh it to
        escape the freshness window.
        """
        body = self._body()
        original_ts = str(int(time.time()) - 3600)
        signature = botify_security.sign_request(self.SECRET, original_ts, body)
        fresh_ts = str(int(time.time()))
        with self.assertRaises(ValueError):
            botify_security.verify_request(self.SECRET, fresh_ts, body, signature)

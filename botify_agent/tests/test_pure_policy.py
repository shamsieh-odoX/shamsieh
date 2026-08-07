"""Stdlib-only, standalone tests for botify_policy.py. Run with plain
python3 -m unittest discover -s tests -p 'test_pure_*.py' — no Odoo needed.
"""

import sys
import os
import hashlib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "models"))

import botify_policy as bp  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
CANONICAL_MANIFEST = os.path.join(REPO_ROOT, "integrations", "odoo", "policy", "policy.manifest.json")
TS_MANIFEST = os.path.join(
    REPO_ROOT, "packages", "api", "src", "services", "odoo", "policy", "policy.manifest.json"
)

FULL_GRANT = {"read", "capture_write", "normal_write", "financial_write", "lifecycle_action", "batch_action"}
READ_ONLY = {"read"}


class TestManifestLockstep(unittest.TestCase):
    def test_local_copy_matches_pinned_hash(self):
        _, sha256 = bp.load_raw_manifest()
        self.assertEqual(sha256, bp.MANIFEST_SHA256)

    def test_matches_canonical_and_ts_copy_in_monorepo_checkout(self):
        if not (os.path.exists(CANONICAL_MANIFEST) and os.path.exists(TS_MANIFEST)):
            self.skipTest("not running inside the full monorepo checkout")
        local_hash = bp.load_raw_manifest()[1]

        def sha(path):
            with open(path, "rb") as fh:
                return hashlib.sha256(fh.read()).hexdigest()

        self.assertEqual(sha(CANONICAL_MANIFEST), local_hash)
        self.assertEqual(sha(TS_MANIFEST), local_hash)


class TestEvaluate(unittest.TestCase):
    def test_blocks_unclassified_model(self):
        with self.assertRaises(bp.PolicyDenied) as ctx:
            bp.evaluate("x_custom_thing", "search_read", granted_op_classes=FULL_GRANT)
        self.assertEqual(ctx.exception.reason, "model_unclassified")

    def test_blocks_hr_contract_even_with_full_grant(self):
        with self.assertRaises(bp.PolicyDenied) as ctx:
            bp.evaluate("hr.contract", "write", fields=["wage"], granted_op_classes=FULL_GRANT)
        self.assertEqual(ctx.exception.reason, "op_class_not_permitted_for_model")

    def test_read_only_grant_allows_read(self):
        result = bp.evaluate("res.partner", "search_read", granted_op_classes=READ_ONLY)
        self.assertEqual(result["opClass"], "read")
        self.assertEqual(result["riskLevel"], "low")

    def test_read_only_grant_rejects_write(self):
        with self.assertRaises(bp.PolicyDenied) as ctx:
            bp.evaluate("res.partner", "write", fields=["name"], granted_op_classes=READ_ONLY)
        self.assertEqual(ctx.exception.reason, "scope_not_granted")

    def test_forbidden_field(self):
        with self.assertRaises(bp.PolicyDenied) as ctx:
            bp.evaluate("res.partner", "write", fields=["name", "password"], granted_op_classes=FULL_GRANT)
        self.assertEqual(ctx.exception.reason, "field_denied")

    def test_workflow_field(self):
        with self.assertRaises(bp.PolicyDenied) as ctx:
            bp.evaluate("sale.order", "write", fields=["state"], granted_op_classes=FULL_GRANT)
        self.assertEqual(ctx.exception.reason, "field_denied")

    def test_workflow_field_allowed_on_create(self):
        # Regression: a real Odoo 18 run (docs/odoo/final-report.md) caught
        # evaluate() applying the workflow-field block to create() too. An
        # initial state/stage_id on CREATE does not skip a lifecycle action's
        # side effects the way a bare write() to an EXISTING record would, so
        # it must stay allowed -- must stay in lockstep with decision.ts.
        result = bp.evaluate("sale.order", "create", fields=["state"], granted_op_classes=FULL_GRANT)
        self.assertEqual(result["opClass"], "normal_write")

    def test_unlink_forbidden(self):
        with self.assertRaises(bp.PolicyDenied) as ctx:
            bp.evaluate("res.partner", "unlink", granted_op_classes=FULL_GRANT)
        self.assertEqual(ctx.exception.reason, "method_forbidden")

    def test_lifecycle_action_allowed(self):
        result = bp.evaluate("sale.order", "action_confirm", granted_op_classes=FULL_GRANT)
        self.assertEqual(result["opClass"], "lifecycle_action")
        self.assertEqual(result["riskLevel"], "medium")

    def test_create_opclass_depends_on_model(self):
        lead = bp.evaluate("crm.lead", "create", granted_op_classes=FULL_GRANT)
        self.assertEqual(lead["opClass"], "capture_write")
        move = bp.evaluate("account.move", "create", granted_op_classes=FULL_GRANT)
        self.assertEqual(move["opClass"], "financial_write")
        self.assertEqual(move["riskLevel"], "high")

    def test_batch_too_large(self):
        with self.assertRaises(bp.PolicyDenied) as ctx:
            bp.evaluate(
                "res.partner", "write", fields=[], op_class_override="batch_action",
                batch_size=999, granted_op_classes=FULL_GRANT,
            )
        self.assertEqual(ctx.exception.reason, "batch_too_large")

    def test_too_many_ids(self):
        with self.assertRaises(bp.PolicyDenied) as ctx:
            bp.evaluate("res.partner", "read", ids=list(range(1, 201)), granted_op_classes=FULL_GRANT)
        self.assertEqual(ctx.exception.reason, "too_many_ids")


if __name__ == "__main__":
    unittest.main()


class TestTenantModelOverlay(unittest.TestCase):
    """Per-tenant custom-model classification (see
    packages/api/src/services/odoo/policy/tenantModels.ts and
    docs/odoo/tenant-models.md).

    This addon is the AUTHORITATIVE enforcement point for end-user-mode
    execution, so the overlay has to work here or the feature does not work at
    all — and, more importantly, its limits have to hold here even if the
    Botify side were fully compromised.
    """

    TODO = {
        "model": "shams.todo.task",
        "opClasses": ["read", "normal_write"],
        "createOpClass": "normal_write",
        "writeOpClass": "normal_write",
        "sensitive": False,
    }

    def _sanitized(self, entry=None, model="shams.todo.task"):
        return bp.sanitize_tenant_model(entry or self.TODO, model)

    def test_sanitizes_a_valid_dotted_custom_model(self):
        got = self._sanitized()
        self.assertIsNotNone(got)
        self.assertEqual(got["opClasses"], ["read", "normal_write"])
        self.assertEqual(got["writeOpClass"], "normal_write")
        self.assertEqual(got["dataClass"], "tenant_custom")

    def test_sanitizes_a_dot_less_studio_model(self):
        # Odoo Studio models are x_-prefixed with no dot; a dotted-only pattern
        # would make every Studio model permanently unclassifiable.
        entry = dict(self.TODO, model="x_membership")
        self.assertIsNotNone(bp.sanitize_tenant_model(entry, "x_membership"))

    def test_rejects_entry_for_a_different_model_than_the_operation(self):
        # The overlay must describe the model actually being operated on;
        # otherwise a grant for model A could carry a classification for B.
        self.assertIsNone(bp.sanitize_tenant_model(self.TODO, "shams.other.model"))

    def test_rejects_globally_classified_models(self):
        # Global manifest supremacy, asserted independently of the Botify side.
        for model in ("res.partner", "account.move", "sale.order", "hr.payslip"):
            entry = dict(self.TODO, model=model)
            self.assertIsNone(bp.sanitize_tenant_model(entry, model), model)

    def test_rejects_reserved_namespaces(self):
        for model in ("res.users", "res.groups", "ir.cron", "mail.message", "ir.config_parameter"):
            entry = dict(self.TODO, model=model)
            self.assertIsNone(bp.sanitize_tenant_model(entry, model), model)

    def test_rejects_malformed_names_and_shapes(self):
        for model in ("Bad.Name", "todo", "_x", "shams..todo", "shams.todo.", "x_" + "a" * 70):
            entry = dict(self.TODO, model=model)
            self.assertIsNone(bp.sanitize_tenant_model(entry, model), model)
        self.assertIsNone(bp.sanitize_tenant_model(None, "shams.todo.task"))
        self.assertIsNone(bp.sanitize_tenant_model("nope", "shams.todo.task"))
        self.assertIsNone(
            bp.sanitize_tenant_model(dict(self.TODO, opClasses=[]), "shams.todo.task")
        )
        self.assertIsNone(
            bp.sanitize_tenant_model(dict(self.TODO, opClasses=["sudo"]), "shams.todo.task")
        )

    def test_falls_back_to_normal_write_for_a_bogus_write_class(self):
        got = bp.sanitize_tenant_model(
            dict(self.TODO, writeOpClass="read", createOpClass="batch_action"),
            "shams.todo.task",
        )
        self.assertEqual(got["writeOpClass"], "normal_write")
        self.assertEqual(got["createOpClass"], "normal_write")

    def test_evaluate_allows_create_on_a_classified_custom_model(self):
        decision = bp.evaluate(
            "shams.todo.task",
            "create",
            fields=["name"],
            granted_op_classes=FULL_GRANT,
            tenant_model=self._sanitized(),
        )
        self.assertEqual(decision["opClass"], "normal_write")
        self.assertEqual(decision["classificationSource"], "tenant")

    def test_evaluate_still_denies_without_an_overlay(self):
        with self.assertRaises(bp.PolicyDenied) as ctx:
            bp.evaluate(
                "shams.todo.task", "create", fields=["name"], granted_op_classes=FULL_GRANT
            )
        self.assertEqual(ctx.exception.reason, "model_unclassified")

    def test_overlay_never_overrides_the_global_manifest(self):
        # Even if a sanitize step were bypassed, evaluate() consults the global
        # manifest first, so a hostile entry for a standard model is inert.
        hostile = {
            "dataClass": "tenant_custom",
            "sensitive": False,
            "createOpClass": "capture_write",
            "writeOpClass": "capture_write",
            "opClasses": ["read", "capture_write", "normal_write"],
            "sensitiveFields": [],
        }
        decision = bp.evaluate(
            "res.partner", "create", fields=["name"],
            granted_op_classes=FULL_GRANT, tenant_model=hostile,
        )
        self.assertEqual(decision["classificationSource"], "global")

    def test_overlay_is_still_subject_to_granted_scopes(self):
        with self.assertRaises(bp.PolicyDenied) as ctx:
            bp.evaluate(
                "shams.todo.task", "create", fields=["name"],
                granted_op_classes={"read"}, tenant_model=self._sanitized(),
            )
        self.assertEqual(ctx.exception.reason, "scope_not_granted")

    def test_overlay_is_still_subject_to_its_own_op_class_list(self):
        read_only = bp.sanitize_tenant_model(
            dict(self.TODO, opClasses=["read"]), "shams.todo.task"
        )
        with self.assertRaises(bp.PolicyDenied) as ctx:
            bp.evaluate(
                "shams.todo.task", "create", fields=["name"],
                granted_op_classes=FULL_GRANT, tenant_model=read_only,
            )
        self.assertEqual(ctx.exception.reason, "op_class_not_permitted_for_model")

    def test_overlay_does_not_bypass_field_and_method_rules(self):
        with self.assertRaises(bp.PolicyDenied) as ctx:
            bp.evaluate(
                "shams.todo.task", "unlink",
                granted_op_classes=FULL_GRANT, tenant_model=self._sanitized(),
            )
        self.assertEqual(ctx.exception.reason, "method_forbidden")

        with self.assertRaises(bp.PolicyDenied) as ctx:
            bp.evaluate(
                "shams.todo.task", "write", fields=["password"],
                granted_op_classes=FULL_GRANT, tenant_model=self._sanitized(),
            )
        self.assertEqual(ctx.exception.reason, "field_denied")

        with self.assertRaises(bp.PolicyDenied) as ctx:
            bp.evaluate(
                "shams.todo.task", "write", fields=["state"],
                granted_op_classes=FULL_GRANT, tenant_model=self._sanitized(),
            )
        self.assertEqual(ctx.exception.reason, "field_denied")

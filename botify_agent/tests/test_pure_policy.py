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

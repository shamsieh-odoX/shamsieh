"""ORM-level tests for the delegation and nonce models.

These specifically exercise the database UNIQUE constraint that IS the
replay defence for every grant-authorized RPC call (docs/odoo/threat-model.md
ยง3.2) \u2014 something the stdlib-only test_pure_* tests cannot do, since they
never touch a real database. Verified against a real, containerized Odoo 18
+ Postgres 16 (addon mounted read-only) — see docs/odoo/runbook.md "Sandbox
verification limits" and docs/odoo/final-report.md for the exact command and
results (3 consecutive clean runs, 0 failed/0 error(s) of 47 tests). To
re-run yourself:

    odoo -d <db> -i botify_agent --test-enable --stop-after-init \
         --test-tags /botify_agent
"""

import datetime

from odoo import fields
from odoo.tests import common, tagged


@tagged("post_install", "-at_install", "botify_agent")
class TestNonceUniqueness(common.TransactionCase):
    def test_duplicate_jti_is_rejected_by_the_database(self):
        """The actual replay defence: a second INSERT of the same jti must
        fail at the database level, not merely be caught by application
        logic that could itself have a bug."""
        Nonce = self.env["botify.agent.nonce"].sudo()
        Nonce.create({"jti": "duplicate-test-jti", "uid": 2, "model": "res.partner", "method": "read"})
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                Nonce.create({"jti": "duplicate-test-jti", "uid": 2, "model": "res.partner", "method": "read"})

    def test_distinct_jtis_are_both_accepted(self):
        Nonce = self.env["botify.agent.nonce"].sudo()
        a = Nonce.create({"jti": "jti-a", "uid": 2})
        b = Nonce.create({"jti": "jti-b", "uid": 2})
        self.assertNotEqual(a.id, b.id)

    def test_concurrent_consumption_only_one_wins(self):
        """Simulates two replicas racing to consume the same grant: the first
        savepoint-wrapped create() succeeds, the second must fail even though
        both observed the jti as "not yet present" before attempting the
        insert \u2014 the UNIQUE index, not a prior SELECT, is what makes this
        safe under concurrency."""
        Nonce = self.env["botify.agent.nonce"].sudo()
        jti = "race-jti"
        Nonce.create({"jti": jti})
        second_failed = False
        try:
            with self.env.cr.savepoint():
                Nonce.create({"jti": jti})
        except Exception:
            second_failed = True
        self.assertTrue(second_failed, "the second consumer of one jti must fail")


@tagged("post_install", "-at_install", "botify_agent")
class TestDelegationLifecycle(common.TransactionCase):
    def _delegation(self, **overrides):
        base = {
            "uid": 2,
            "installation_id": "conn-1",
            "agent_id": "agent-1",
            "secret_key": "test-delegation-key",
            "expires_at": fields.Datetime.now() + datetime.timedelta(minutes=15),
        }
        base.update(overrides)
        return self.env["botify.agent.delegation"].sudo().create(base)

    def test_fresh_delegation_is_live(self):
        d = self._delegation()
        self.assertTrue(d.is_live())

    def test_expired_delegation_is_not_live(self):
        d = self._delegation(expires_at=fields.Datetime.now() - datetime.timedelta(minutes=1))
        self.assertFalse(d.is_live())

    def test_revoked_delegation_is_not_live_even_if_unexpired(self):
        d = self._delegation()
        d.write({"revoked_at": fields.Datetime.now()})
        self.assertFalse(d.is_live())

    def test_no_group_has_direct_read_access(self):
        """Only base.group_system gets an ACL row (security/ir.model.access.csv);
        a plain employee querying this model via the ORM under with_user()
        must be denied, exactly like the pre-existing shared-secret storage
        pattern in ir.config_parameter."""
        from ._helpers import user_group_field

        employee = self.env["res.users"].create({
            "name": "No Delegation Access",
            "login": "botify.nodelegaccess@example.com",
            user_group_field(self.env): [(6, 0, [self.env.ref("base.group_user").id])],
        })
        d = self._delegation()
        from odoo.exceptions import AccessError

        with self.assertRaises(AccessError):
            self.env["botify.agent.delegation"].with_user(employee).browse(d.id).read(["secret_key"])

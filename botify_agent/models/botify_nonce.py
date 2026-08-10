"""Single-use grant-jti ledger — the actual replay defence for every RPC call.

Every grant token carries a `jti`. Before executing the operation it
authorizes, the RPC controller atomically INSERTs the jti here; the model's
own SQL UNIQUE constraint makes a second insert of the same jti fail with an
IntegrityError, which the controller turns into `grant_replayed`. This is
deliberately a plain INSERT-based check, not a SELECT-then-INSERT: the
uniqueness constraint at the database level is what makes it safe under
concurrent requests (two workers racing to consume the same jti can only ever
have one INSERT succeed), closing the gap the old shared-secret RPC path left
open (the signed `nonce` field that was never checked — see
docs/odoo/threat-model.md §3.2).

Access control: security/ir.model.access.csv grants base.group_system a
read-only ACL row (support/troubleshooting only) and no other group any rule
at all — a full deny for everyone else, matching botify.agent.delegation.
"""

from odoo import fields, models


class BotifyAgentNonce(models.Model):
    _name = "botify.agent.nonce"
    _description = "Consumed Botify grant jti (replay defence)"
    _rec_name = "jti"

    jti = fields.Char(required=True, index=True)
    uid = fields.Integer(help="Acting uid, for audit only.")
    model = fields.Char(help="Target model, for audit only.")
    method = fields.Char(help="Target method, for audit only.")
    consumed_at = fields.Datetime(default=fields.Datetime.now, required=True)

    # Deliberately NOT declared via either Odoo constraint API: the pre-19
    # declarative style (`_sql_constraints = [(name, sql, message)]`) is
    # silently ignored by Odoo 19+ — add_to_registry() only logs a warning,
    # never raises, so the UNIQUE constraint simply never gets created and a
    # duplicate jti insert silently succeeds (verified live against a real
    # Odoo 19 instance: this is exactly what happened before this fix). The
    # 19+ replacement (`models.Constraint(...)`) does not exist as an
    # importable class on Odoo 18. A raw `ALTER TABLE ... ADD CONSTRAINT` in
    # init() sidesteps both declarative APIs and is identical on every Odoo
    # version this addon targets — the same pattern Odoo core itself uses in
    # addons/base/models/ir_config_parameter.py for its own unique key.
    def init(self):
        self.env.cr.execute(
            "SELECT 1 FROM pg_constraint WHERE conname = 'botify_agent_nonce_jti_unique'"
        )
        if not self.env.cr.fetchone():
            self.env.cr.execute(
                "ALTER TABLE botify_agent_nonce "
                "ADD CONSTRAINT botify_agent_nonce_jti_unique UNIQUE (jti)"
            )

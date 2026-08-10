"""Per-user delegation credential, minted alongside an identity assertion.

A delegation record is the second of the three credential layers described in
docs/odoo/architecture.md ยง1: it proves "Botify holds a credential Odoo
minted for THIS specific user, THIS session" — narrower than the
installation-wide shared secret, broader than a single grant.

The raw key is generated here, stored on this record and returned to Botify
exactly once, at mint time. It is readable only via sudo() from addon
controller code: security/ir.model.access.csv grants base.group_system a
read-only ACL row (for support/troubleshooting by a system administrator)
and grants NO other group any rule at all, which Odoo treats as a full deny —
a regular employee (or a compromised low-privilege session) cannot read
another user's delegation key through the ORM or the web client, even though
the model is installed. This mirrors the existing shared-secret pattern in
res_config_settings.py (ir.config_parameter, group_system-only).
Botify stores it AES-encrypted on IdentitySession and never sends it over the
wire again — it only proves possession by HMAC-signing grant requests with
it (botify_agent.controllers.grant), which this model's key never leaves
Odoo to verify.
"""

from odoo import fields, models


class BotifyAgentDelegation(models.Model):
    _name = "botify.agent.delegation"
    _description = "Botify per-user delegation credential"
    _rec_name = "id"

    uid = fields.Integer(required=True, index=True, help="res.users id this delegation acts for.")
    installation_id = fields.Char(required=True, index=True)
    agent_id = fields.Char(required=True)
    # Base64/hex secret used as the HMAC key for grant-request proof-of-
    # possession. Never exposed by any route after issuance.
    secret_key = fields.Char(required=True)
    allowed_company_ids = fields.Char(
        default="[]", help="JSON list of company ids this delegation may request grants for."
    )
    scopes = fields.Char(
        default='["read","capture_write","normal_write","financial_write","lifecycle_action","batch_action"]',
        help="JSON list of op classes this delegation may request grants for. See "
        "docs/odoo/architecture.md \u00a72 \u2014 the true per-agent restriction is enforced "
        "Botify-side before a grant is ever requested; this is a second, Odoo-side ceiling.",
    )
    expires_at = fields.Datetime(required=True, index=True)
    revoked_at = fields.Datetime()
    created_at = fields.Datetime(default=fields.Datetime.now)
    last_used_at = fields.Datetime()

    def is_live(self):
        self.ensure_one()
        if self.revoked_at:
            return False
        if not self.expires_at or self.expires_at < fields.Datetime.now():
            return False
        return True

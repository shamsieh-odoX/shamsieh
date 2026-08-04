from odoo import api, fields, models
from odoo.exceptions import ValidationError

from . import botify_security


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Stored in ir.config_parameter, whose ACL grants access to base.group_system
    # only (odoo/addons/base/security/ir.model.access.csv). A regular employee
    # therefore cannot read the shared secret through the ORM or the web client,
    # which is what keeps it out of the browser.
    botify_base_url = fields.Char(
        string="Botify API base URL",
        config_parameter="botify_agent.base_url",
        default="https://botifyarabia.ai/api",
        help="e.g. https://botifyarabia.ai/api",
    )
    botify_agent_id = fields.Char(
        string="Botify agent ID",
        config_parameter="botify_agent.agent_id",
        help="UUID of the Botify agent this Odoo instance talks to.",
    )
    botify_installation_id = fields.Char(
        string="Botify connection ID",
        config_parameter="botify_agent.installation_id",
        help="UUID of the Odoo connection record in Botify (the installation).",
    )
    botify_shared_secret = fields.Char(
        string="Shared secret",
        config_parameter="botify_agent.shared_secret",
        help="Signs identity assertions and authenticates Botify's calls back "
             "into this database. Never expose it to the browser.",
    )
    botify_assertion_ttl = fields.Integer(
        string="Assertion lifetime (seconds)",
        config_parameter="botify_agent.assertion_ttl",
        default=120,
        help="How long a minted identity assertion stays valid. Keep it short — "
             "it is single-use and only has to survive one round trip.",
    )
    botify_allowed_group_id = fields.Many2one(
        "res.groups",
        string="Restrict to group",
        config_parameter="botify_agent.allowed_group_id",
        help="Optional. When set, only members of this group may obtain an "
             "identity assertion. Use it to roll the agent out gradually — it "
             "does NOT grant anything, it only narrows who can start a session.",
    )
    botify_enabled = fields.Boolean(
        string="Enable Botify agent",
        config_parameter="botify_agent.enabled",
        default=True,
    )

    @api.constrains("botify_assertion_ttl")
    def _check_assertion_ttl(self):
        for record in self:
            ttl = record.botify_assertion_ttl
            # Upper bound mirrors MAX_ASSERTION_TTL_SECONDS on the Botify side;
            # a longer one would simply be rejected there, so fail loudly here.
            if ttl and not (30 <= ttl <= 300):
                raise ValidationError(
                    "Assertion lifetime must be between 30 and 300 seconds."
                )

    def action_botify_generate_secret(self):
        """Mint a fresh shared secret.

        Rotation procedure: generate here, paste into Botify, save. Sessions
        already issued keep working (Botify holds its own session tokens); only
        assertions minted with the old secret stop verifying, which is a window
        of seconds.
        """
        self.ensure_one()
        secret = botify_security.new_nonce() + botify_security.new_nonce()
        self.env["ir.config_parameter"].sudo().set_param(
            "botify_agent.shared_secret", secret
        )
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

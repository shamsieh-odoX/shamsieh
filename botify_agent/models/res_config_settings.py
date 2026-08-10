import time

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
        help="e.g. https://api.botifyarabia.ai",
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
        default=False,
    )
    botify_allow_custom_models = fields.Boolean(
        string="Allow assistant writes to custom models",
        config_parameter="botify_agent.allow_custom_models",
        default=False,
        help="Off by default. The shared policy manifest classifies standard Odoo "
             "models only, so writes to this database's OWN custom models "
             "(developer modules or Studio objects) are refused unless you turn "
             "this on AND classify the specific models in Botify. This switch is "
             "the Odoo-side half of that decision: it cannot be set from Botify, "
             "so nothing outside this database can unlock custom-model writes on "
             "its own. It grants nothing by itself, and Odoo's own access rights "
             "and record rules still decide every individual operation.",
    )
    botify_grant_ttl = fields.Integer(
        string="Grant lifetime (seconds)",
        config_parameter="botify_agent.grant_ttl",
        default=90,
        help="How long a per-operation grant stays valid. Freshly minted per tool "
             "call — keep it short, it only has to survive one round trip.",
    )
    botify_secret_previous = fields.Char(
        string="Previous shared secret (rotation grace window)",
        config_parameter="botify_agent.shared_secret_previous",
        readonly=True,
        help="Set automatically when you rotate the shared secret. Accepted "
             "alongside the current secret until the grace window elapses.",
    )
    botify_secret_grace_hours = fields.Integer(
        string="Secret rotation grace window (hours)",
        config_parameter="botify_agent.secret_grace_hours",
        default=24,
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
        """Rotate the shared secret with a grace window (AC-25).

        Rotation procedure: the CURRENT secret moves to "previous" (with a
        timestamp), a fresh secret becomes current, and the operator pastes
        the new one into Botify. Until the grace window
        (botify_agent.secret_grace_hours, default 24h) elapses,
        /botify_agent/grant and /botify_agent/rpc accept EITHER secret—so an
        in-flight Botify replica that hasn't picked up the new value yet does
        not start failing every call the instant you rotate. This is
        operator-triggered and left in Odoo's own "Settings changed" trail via
        the normal ir.config_parameter write; a dedicated Botify-side audit
        entry is also recorded for the connection when Botify's rotation
        endpoint is used (see docs/odoo/runbook.md \"Key rotation\").
        """
        self.ensure_one()
        params = self.env["ir.config_parameter"].sudo()
        current = params.get_param("botify_agent.shared_secret") or ""
        if current:
            params.set_param("botify_agent.shared_secret_previous", current)
            params.set_param("botify_agent.secret_rotated_at", str(int(time.time())))
        secret = botify_security.new_nonce() + botify_security.new_nonce()
        params.set_param("botify_agent.shared_secret", secret)
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

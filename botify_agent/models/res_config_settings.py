from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    botify_enabled = fields.Boolean("Botify agent", config_parameter="botify_agent.enabled")
    botify_api_url = fields.Char("Botify API URL", config_parameter="botify_agent.api_url")
    botify_installation_key = fields.Char("Installation key", config_parameter="botify_agent.installation_key")
    botify_secret = fields.Char("Installation secret", config_parameter="botify_agent.secret", groups="base.group_system")
    botify_allow_low_write = fields.Boolean("Low-risk changes", config_parameter="botify_agent.allow_low_write")
    botify_allow_high_write = fields.Boolean("High-impact changes", config_parameter="botify_agent.allow_high_write")
    botify_allow_financial = fields.Boolean("Financial operations", config_parameter="botify_agent.allow_financial")
    botify_allow_destructive = fields.Boolean("Deletions and cancellations", config_parameter="botify_agent.allow_destructive")
    botify_allow_external_communication = fields.Boolean(
        "Messages to external people", config_parameter="botify_agent.allow_external_communication"
    )
    botify_retention_days = fields.Integer("Keep the operation log (days)", config_parameter="botify_agent.retention_days", default=90)

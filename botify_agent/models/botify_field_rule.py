from odoo import fields, models

from .botify_method import RISK_SELECTION


class BotifyAgentFieldRule(models.Model):
    """This database's own field risks (e.g. a custom approval field is
    financial). Stricter always wins over the platform baseline."""

    _name = "botify.agent.field_rule"
    _description = "Botify agent field risk rule"
    _order = "model, field"

    model = fields.Char(required=True)
    field = fields.Char(required=True)
    risk_class = fields.Selection(RISK_SELECTION, required=True, default="high_write")

    _unique_field = models.Constraint("unique(model, field)", "One rule per field.")

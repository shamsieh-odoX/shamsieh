import json

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..services import params
from ..services.classify import RISK_CLASSES
from ..services.executor import METHOD, MODEL

RISK_SELECTION = [(value, value.replace("_", " ").title()) for value in RISK_CLASSES if value != "read"]


class BotifyAgentMethod(models.Model):
    """A business method the agent may call on a model, with its argument
    contract. Anything not listed (or inactive) is denied."""

    _name = "botify.agent.method"
    _description = "Botify agent business method"
    _order = "model, method"

    model = fields.Char(required=True, help="Technical model name, e.g. sale.order")
    method = fields.Char(required=True, help="Public method name, e.g. action_confirm")
    risk_class = fields.Selection(RISK_SELECTION, required=True, default="high_write")
    description = fields.Char()
    params_schema = fields.Text(
        required=True,
        default='{"type": "object", "properties": {}}',
        help="JSON Schema (strict subset) of the keyword arguments; unknown arguments are refused.",
    )
    record_arity = fields.Selection([("one", "Exactly one record"), ("many", "One or more records")], required=True, default="one")
    max_records = fields.Integer(default=1, required=True)
    active = fields.Boolean(default=True)

    _unique_method = models.Constraint("unique(model, method)", "A method is registered once per model.")

    def schema(self):
        self.ensure_one()
        schema = json.loads(self.params_schema)
        # Unknown arguments are always refused, whatever the row says.
        schema["additionalProperties"] = False
        return schema

    @api.constrains("model", "method", "params_schema", "record_arity", "max_records")
    def _check_contract(self):
        for row in self:
            if not MODEL.match(row.model or ""):
                raise ValidationError(self.env._("%s is not a model name", row.model))
            if not METHOD.match(row.method or ""):
                raise ValidationError(self.env._("Only public methods can be registered."))
            # ORM methods (write, unlink, sudo, with_user…) are never business actions.
            if hasattr(models.BaseModel, row.method):
                raise ValidationError(self.env._("%s is a generic ORM method, not a business action", row.method))
            try:
                schema = json.loads(row.params_schema)
            except ValueError as error:
                raise ValidationError(self.env._("The params schema is not valid JSON.")) from error
            problem = params.check_schema(schema)
            if problem:
                raise ValidationError(problem)
            if not 1 <= row.max_records <= 50 or (row.record_arity == "one" and row.max_records != 1):
                raise ValidationError(self.env._("Record limits must be 1 for one record, at most 50 otherwise."))

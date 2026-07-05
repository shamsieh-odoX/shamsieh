# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


class HrOvertimeType(models.Model):
    _name = 'hr.overtime.type'
    _description = 'Overtime Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)
    category = fields.Selection(
        selection=[
            ('regular', 'Regular Working Day'),
            ('weekend', 'Weekend'),
            ('day_off', 'Day Off / Public Holiday'),
        ],
        string='Category',
        required=True,
        default='regular',
        help='Used to automatically pick this type based on the overtime date.',
    )
    rate_multiplier = fields.Float(
        string='Rate Multiplier',
        default=1.5,
        required=True,
        help='Pay rate multiplier applied to the base hourly cost (e.g. 1.5 for time-and-a-half).',
    )
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)',
        'The overtime type code must be unique per company.',
    )
    _rate_multiplier_positive = models.Constraint(
        'CHECK(rate_multiplier > 0)',
        'The rate multiplier must be strictly positive.',
    )

    @api.constrains('rate_multiplier')
    def _check_rate_multiplier(self):
        for overtime_type in self:
            if overtime_type.rate_multiplier <= 0:
                raise ValidationError(_('The rate multiplier must be strictly positive.'))

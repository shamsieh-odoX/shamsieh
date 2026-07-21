# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

CATEGORY_DEFAULTS = {
    'regular': {'name': 'Regular Overtime', 'code': 'regular', 'rate_multiplier': 1.5, 'sequence': 1},
    'weekend': {'name': 'Weekend Overtime', 'code': 'weekend', 'rate_multiplier': 2.0, 'sequence': 2},
    'day_off': {'name': 'Day Off Overtime', 'code': 'holiday', 'rate_multiplier': 2.5, 'sequence': 3},
}


class HrOvertimeType(models.Model):
    _name = 'hr.overtime.type'
    _description = 'Overtime Type'
    _order = 'company_id, sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        help='Technical code used internally (regular, weekend, holiday).',
    )
    category = fields.Selection(
        selection=[
            ('regular', 'Regular Working Day'),
            ('weekend', 'Weekend'),
            ('day_off', 'Day Off / Public Holiday'),
        ],
        string='Category',
        required=True,
        default='regular',
        help='Each company branch should have exactly one active type per category. '
             'The rate multiplier on that record is used for automatic cost calculation.',
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
        string='Company Branch',
        default=lambda self: self.env.company,
        index=True,
        help='Leave empty only for shared template records. Each branch should have its own set.',
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

    @api.onchange('category')
    def _onchange_category(self):
        defaults = CATEGORY_DEFAULTS.get(self.category)
        if defaults:
            self.name = defaults['name']
            self.code = defaults['code']
            self.rate_multiplier = defaults['rate_multiplier']
            self.sequence = defaults['sequence']

    @api.constrains('rate_multiplier')
    def _check_rate_multiplier(self):
        for overtime_type in self:
            if overtime_type.rate_multiplier <= 0:
                raise ValidationError(_('The rate multiplier must be strictly positive.'))

    @api.constrains('category', 'company_id', 'active')
    def _check_one_category_per_company(self):
        for overtime_type in self.filtered('active'):
            company_ref = overtime_type.company_id.id if overtime_type.company_id else False
            duplicate = self.search([
                ('id', '!=', overtime_type.id),
                ('category', '=', overtime_type.category),
                ('active', '=', True),
                ('company_id', '=', company_ref),
            ], limit=1)
            if duplicate:
                company_label = overtime_type.company_id.display_name if overtime_type.company_id else _('Shared')
                raise ValidationError(_(
                    'Only one active overtime type is allowed per category for %(company)s. '
                    'Edit the existing %(category)s type or archive it first.',
                    company=company_label,
                    category=dict(self._fields['category'].selection).get(overtime_type.category),
                ))

    @api.model
    def _create_for_company(self, company, category):
        defaults = CATEGORY_DEFAULTS[category]
        return self.create({
            'name': defaults['name'],
            'code': defaults['code'],
            'category': category,
            'rate_multiplier': defaults['rate_multiplier'],
            'sequence': defaults['sequence'],
            'company_id': company.id,
            'active': True,
        })

# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    payroll_daily_wage_divisor = fields.Integer(
        related='company_id.payroll_daily_wage_divisor',
        readonly=False,
    )
    payroll_absence_deduction_enabled = fields.Boolean(
        related='company_id.payroll_absence_deduction_enabled',
        readonly=False,
    )

    def action_open_jordan_rule_parameters(self):
        self.ensure_one()
        return {
            'name': 'Jordan Rule Parameters',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.rule.parameter',
            'view_mode': 'list,form',
            'domain': [('country_id.code', '=', 'JO')],
            'context': {'default_country_id': self.env.ref('base.jo').id},
        }

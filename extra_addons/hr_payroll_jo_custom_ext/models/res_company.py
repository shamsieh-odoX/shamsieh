# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    payroll_daily_wage_divisor = fields.Integer(
        string='Payroll Daily Wage Divisor',
        default=30,
        help='Daily rate = monthly wage divided by this value (Jordan standard: 30).',
    )
    payroll_absence_deduction_enabled = fields.Boolean(
        string='Deduct Absence Days on Payslip',
        default=True,
    )

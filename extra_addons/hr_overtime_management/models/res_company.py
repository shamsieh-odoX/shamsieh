# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    overtime_generate_analytic_line = fields.Boolean(
        string='Generate Timesheet on Overtime Approval',
        default=True,
    )
    overtime_default_type_id = fields.Many2one(
        'hr.overtime.type',
        string='Regular Overtime Type',
        domain="['|', ('company_id', '=', False), ('company_id', '=', id), ('category', '=', 'regular')]",
        help='Applied on regular working days (Sunday–Thursday by default).',
    )
    overtime_weekend_type_id = fields.Many2one(
        'hr.overtime.type',
        string='Weekend Overtime Type',
        domain="['|', ('company_id', '=', False), ('company_id', '=', id), ('category', '=', 'weekend')]",
        help='Applied when overtime falls on a configured weekend day.',
    )
    overtime_holiday_type_id = fields.Many2one(
        'hr.overtime.type',
        string='Day Off Overtime Type',
        domain="['|', ('company_id', '=', False), ('company_id', '=', id), ('category', '=', 'day_off')]",
        help='Applied when overtime falls on a public holiday or calendar day off.',
    )
    overtime_weekend_weekdays = fields.Char(
        string='Weekend Weekdays',
        default='4,5',
        help='Comma-separated weekday numbers (Monday=0 … Sunday=6). '
             'Default 4,5 = Friday and Saturday.',
    )
    overtime_daily_hours_cap = fields.Float(
        string='Daily Overtime Hours Warning Cap',
        default=4.0,
        help='Display a warning when a single request exceeds this number of hours.',
    )
    overtime_hours_per_month = fields.Float(
        string='Working Hours per Month',
        default=173.33,
        help='Fallback divisor to derive hourly cost from monthly contract wage (wage / hours).',
    )

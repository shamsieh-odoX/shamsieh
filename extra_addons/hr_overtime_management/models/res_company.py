# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

_OVERTIME_TYPE_FIELDS = {
    'regular': 'overtime_default_type_id',
    'weekend': 'overtime_weekend_type_id',
    'day_off': 'overtime_holiday_type_id',
}


class ResCompany(models.Model):
    _inherit = 'res.company'

    overtime_generate_analytic_line = fields.Boolean(
        string='Generate Timesheet on Overtime Approval',
        default=True,
    )
    overtime_default_type_id = fields.Many2one(
        'hr.overtime.type',
        string='Regular Overtime Type',
        domain="['&', '|', ('company_id', '=', False), ('company_id', '=', id), ('category', '=', 'regular')]",
        help='Applied on regular working days (Sunday–Thursday by default).',
    )
    overtime_weekend_type_id = fields.Many2one(
        'hr.overtime.type',
        string='Weekend Overtime Type',
        domain="['&', '|', ('company_id', '=', False), ('company_id', '=', id), ('category', '=', 'weekend')]",
        help='Applied when overtime falls on a configured weekend day.',
    )
    overtime_holiday_type_id = fields.Many2one(
        'hr.overtime.type',
        string='Day Off Overtime Type',
        domain="['&', '|', ('company_id', '=', False), ('company_id', '=', id), ('category', '=', 'day_off')]",
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

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies._ensure_overtime_types()
        return companies

    @api.model
    def _ensure_overtime_types_for_all_companies(self):
        self.search([])._ensure_overtime_types()

    def _ensure_overtime_types(self):
        OvertimeType = self.env['hr.overtime.type'].sudo()
        for company in self:
            updates = {}
            for category, field_name in _OVERTIME_TYPE_FIELDS.items():
                ot_type = OvertimeType.search([
                    ('company_id', '=', company.id),
                    ('category', '=', category),
                    ('active', '=', True),
                ], limit=1)
                if not ot_type:
                    ot_type = OvertimeType._create_for_company(company, category)
                if not company[field_name]:
                    updates[field_name] = ot_type.id
            if updates:
                company.sudo().write(updates)

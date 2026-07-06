# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    overtime_generate_analytic_line = fields.Boolean(
        related='company_id.overtime_generate_analytic_line',
        readonly=False,
    )
    overtime_default_type_id = fields.Many2one(
        related='company_id.overtime_default_type_id',
        readonly=False,
        domain="['&', '|', ('company_id', '=', False), ('company_id', '=', company_id), ('category', '=', 'regular')]",
    )
    overtime_weekend_type_id = fields.Many2one(
        related='company_id.overtime_weekend_type_id',
        readonly=False,
        domain="['&', '|', ('company_id', '=', False), ('company_id', '=', company_id), ('category', '=', 'weekend')]",
    )
    overtime_holiday_type_id = fields.Many2one(
        related='company_id.overtime_holiday_type_id',
        readonly=False,
        domain="['&', '|', ('company_id', '=', False), ('company_id', '=', company_id), ('category', '=', 'day_off')]",
    )
    overtime_weekend_weekdays = fields.Char(
        related='company_id.overtime_weekend_weekdays',
        readonly=False,
    )
    overtime_daily_hours_cap = fields.Float(
        related='company_id.overtime_daily_hours_cap',
        readonly=False,
    )
    overtime_hours_per_month = fields.Float(
        related='company_id.overtime_hours_per_month',
        readonly=False,
    )
    module_hr_overtime_payroll = fields.Boolean(
        string='Link Overtime to Payroll',
        help='Install the payroll glue module to push approved overtime costs to payslips.',
    )

    @api.model
    def _is_payroll_installed(self):
        module = self.env['ir.module.module'].sudo().search([
            ('name', '=', 'hr_payroll'),
            ('state', '=', 'installed'),
        ], limit=1)
        return bool(module)

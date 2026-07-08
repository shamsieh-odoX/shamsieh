# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    sick_leave_days_per_year = fields.Integer(
        string='Sick Leave Days Per Year',
        default=14,
        help='Number of sick leave days allocated to each active employee on annual renewal.',
    )
    annual_leave_days_per_year = fields.Integer(
        string='Annual Leave Days Per Year',
        default=21,
        help='Fixed annual leave days granted to each active employee at year start.',
    )
    annual_leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='Annual Leave Type',
        domain="[('requires_allocation', '=', True), '|', ('company_id', '=', False), ('company_id', '=', id)]",
        help='Time off type used for annual leave grants and carryover.',
    )

    def _get_annual_leave_type(self):
        self.ensure_one()
        if self.annual_leave_type_id:
            return self.annual_leave_type_id
        return self.env.ref('hr_holidays.leave_type_paid_time_off', raise_if_not_found=False)

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
    annual_leave_carryover_max_days = fields.Integer(
        string='Max Carryover Days',
        default=0,
        help='Maximum unused annual leave days carried into the new year per employee. '
             'Set to 0 for no limit.',
    )
    hourly_departure_type_id = fields.Many2one(
        'hr.leave.type',
        string='Hourly Departure Leave Type',
        domain="['|', ('company_id', '=', False), ('company_id', '=', id)]",
        help='Time off type used for Article 11 hourly departures.',
    )
    hourly_departure_max_hours_day = fields.Float(
        string='Max Departure Hours Per Day',
        default=3.0,
        help='Maximum hourly departure hours allowed per employee per calendar day.',
    )
    hourly_departure_max_hours_month = fields.Float(
        string='Max Departure Hours Per Month',
        default=6.0,
        help='Maximum hourly departure hours allocated and allowed per employee per month.',
    )

    def _get_annual_leave_type(self):
        self.ensure_one()
        if self.annual_leave_type_id:
            return self.annual_leave_type_id
        return self.env.ref('hr_holidays.leave_type_paid_time_off', raise_if_not_found=False)

    def _get_hourly_departure_type(self):
        self.ensure_one()
        if self.hourly_departure_type_id:
            return self.hourly_departure_type_id
        return self.env.ref(
            'hr_holidays_custom_ext.leave_type_hourly_departure',
            raise_if_not_found=False,
        )

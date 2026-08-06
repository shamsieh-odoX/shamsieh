# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrHourlyDepartureConversion(models.Model):
    _name = 'hr.hourly.departure.conversion'
    _description = 'Hourly Departure to Annual Leave Conversion'
    _order = 'create_date desc, id desc'

    employee_id = fields.Many2one(
        'hr.employee',
        required=True,
        index=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        'res.company',
        related='employee_id.company_id',
        store=True,
        index=True,
    )
    annual_leave_id = fields.Many2one(
        'hr.leave',
        string='Annual Leave',
        required=True,
        ondelete='restrict',
        index=True,
    )
    trigger_leave_id = fields.Many2one(
        'hr.leave',
        string='Trigger Departure',
        ondelete='set null',
        index=True,
        help='Departure request that caused the accumulator to reach one work day.',
    )
    hours_converted = fields.Float(
        string='Hours Converted',
        required=True,
    )
    state = fields.Selection(
        selection=[
            ('done', 'Done'),
            ('reversed', 'Reversed'),
        ],
        default='done',
        required=True,
        index=True,
    )

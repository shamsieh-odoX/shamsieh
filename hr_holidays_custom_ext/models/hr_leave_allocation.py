# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    allocation_origin = fields.Selection(
        selection=[
            ('manual', 'Manual'),
            ('annual_grant', 'Annual Grant'),
            ('year_carryover', 'Year Carryover'),
            ('sick_renewal', 'Sick Leave Renewal'),
            ('hourly_departure_monthly', 'Hourly Departure Monthly'),
            ('overtime_request', 'Overtime Request'),
        ],
        string='Allocation Origin',
        default='manual',
        index=True,
    )
    origin_year = fields.Integer(
        string='Origin Year',
        index=True,
        help='Calendar year this automated allocation belongs to.',
    )
    origin_month = fields.Integer(
        string='Origin Month',
        index=True,
        help='Calendar month (1-12) this automated monthly allocation belongs to.',
    )
    overtime_request_id = fields.Many2one(
        'hr.overtime.request',
        string='Overtime Request',
        index=True,
        ondelete='set null',
        help='Source overtime request that generated this allocation.',
    )

# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    allocation_origin = fields.Selection(
        selection=[
            ('manual', 'Manual'),
            ('annual_grant', 'Annual Grant'),
            ('year_carryover', 'Year Carryover'),
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

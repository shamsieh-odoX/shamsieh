# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    is_hourly_departure = fields.Boolean(
        string='Hourly Departure (Article 11)',
        default=False,
        help='Enforce Article 11 hourly departure caps and annual leave conversion.',
    )

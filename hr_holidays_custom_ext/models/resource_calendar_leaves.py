# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResourceCalendarLeaves(models.Model):
    _inherit = 'resource.calendar.leaves'

    exceptional_holiday_id = fields.Many2one(
        'hr.exceptional.holiday',
        string='Exceptional Holiday Request',
        readonly=True,
        copy=False,
    )

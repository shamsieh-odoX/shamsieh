# -*- coding: utf-8 -*-

from odoo import fields, models


class ResourceCalendarAttendance(models.Model):
    _inherit = 'resource.calendar.attendance'

    location_type = fields.Selection(
        selection=[
            ('office', 'Office'),
            ('home', 'Home'),
            ('other', 'Other'),
        ],
        string='Attendance Location',
        default='office',
        required=True,
        help='Defines where employees are expected to work for this schedule line.',
    )

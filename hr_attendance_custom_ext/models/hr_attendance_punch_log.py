# -*- coding: utf-8 -*-

from odoo import fields, models


class HrAttendancePunchLog(models.Model):
    _name = 'hr.attendance.punch.log'
    _description = 'Attendance Punch Log'
    _order = 'punch_time desc, id desc'

    attendance_id = fields.Many2one(
        'hr.attendance',
        required=True,
        ondelete='cascade',
        index=True,
    )
    employee_id = fields.Many2one(
        related='attendance_id.employee_id',
        store=True,
        index=True,
    )
    punch_type = fields.Selection(
        selection=[
            ('check_in', 'Check In'),
            ('break_out', 'Break Out'),  # start break
            ('break_in', 'Break In'),    # end break
            ('check_out', 'Check Out'),
        ],
        required=True,
        index=True,
        help='Break Out starts a break; Break In ends a break.',
    )
    punch_time = fields.Datetime(required=True, index=True)
    attendance_source = fields.Selection(
        selection=[
            ('fingerprint', 'Fingerprint'),
            ('face', 'Face'),
            ('pin', 'PIN'),
            ('manual', 'Manual'),
            ('kiosk', 'Kiosk'),
            ('systray', 'Systray'),
        ],
        default='fingerprint',
    )
    device_user_id = fields.Char(index=True)
    external_log_id = fields.Char(index=True)

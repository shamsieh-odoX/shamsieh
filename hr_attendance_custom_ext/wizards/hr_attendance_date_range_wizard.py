# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class HrAttendanceDateRangeWizard(models.TransientModel):
    _name = 'hr.attendance.date.range.wizard'
    _description = 'Attendance Report Date Range'

    date_from = fields.Date(
        string='Date From',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        default=fields.Date.today,
    )

    def action_open_report(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(_('Date To must be on or after Date From.'))
        action = self.env.ref('hr_attendance.hr_attendance_reporting').sudo().read()[0]
        action['domain'] = [
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        action['context'] = {
            'search_default_employee': 1,
            'search_default_activeemployees': 1,
            'attendance_date_from': fields.Date.to_string(self.date_from),
            'attendance_date_to': fields.Date.to_string(self.date_to),
        }
        action['name'] = _(
            'Attendances (%(date_from)s → %(date_to)s)',
            date_from=self.date_from,
            date_to=self.date_to,
        )
        return action

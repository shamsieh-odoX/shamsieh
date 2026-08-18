# -*- coding: utf-8 -*-

from datetime import datetime, time, timedelta

import pytz
from pytz import timezone as pytz_timezone, utc

from odoo import api, fields, models


class HrAttendanceDailyStatus(models.Model):
    _name = 'hr.attendance.daily.status'
    _description = 'Daily Attendance Status'
    _order = 'date desc, employee_id'
    _rec_name = 'display_name'

    employee_id = fields.Many2one('hr.employee', required=True, index=True, ondelete='cascade')
    date = fields.Date(required=True, index=True)
    company_id = fields.Many2one(related='employee_id.company_id', store=True, index=True)
    department_id = fields.Many2one(related='employee_id.department_id', store=True, index=True)
    calendar_id = fields.Many2one('resource.calendar', string='Working Schedule')
    status = fields.Selection(
        selection=[
            ('present', 'Present'),
            ('late', 'Late'),
            ('early_leave', 'Early Leave'),
            ('absent', 'Absent'),
            ('incomplete', 'Incomplete'),
            ('on_leave', 'On Leave'),
            ('on_holiday', 'Public Holiday'),
        ],
        required=True,
        index=True,
    )
    is_on_approved_leave = fields.Boolean(
        string='On Approved Leave',
        index=True,
        help='Employee had a validated time off request on this date.',
    )
    is_public_holiday = fields.Boolean(
        string='Public Holiday',
        index=True,
        help='Date is a company or calendar public holiday.',
    )
    check_in = fields.Datetime()
    check_out = fields.Datetime()
    late_minutes = fields.Integer()
    early_checkout_minutes = fields.Integer()
    extra_minutes = fields.Integer()
    billable_late_minutes = fields.Integer()
    unworked_minutes = fields.Integer()
    worked_hours = fields.Float()
    source_summary = fields.Char(
        help='Comma-separated attendance sources for the day.',
    )
    notes = fields.Text()
    display_name = fields.Char(compute='_compute_display_name')

    _employee_date_uniq = models.Constraint(
        'unique(employee_id, date)',
        'Daily status must be unique per employee and date.',
    )

    @api.depends('employee_id', 'date', 'status')
    def _compute_display_name(self):
        for record in self:
            record.display_name = '%s — %s (%s)' % (
                record.employee_id.name or '',
                record.date or '',
                record.status or '',
            )

    def _is_working_day(self, employee, target_date):
        calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id
        if not calendar:
            return True
        tz_name = employee.tz or calendar.tz or 'UTC'
        tz = pytz_timezone(tz_name)
        day_start = tz.localize(datetime.combine(target_date, time.min))
        day_end = tz.localize(datetime.combine(target_date, time.max))
        intervals = calendar._attendance_intervals_batch(
            day_start, day_end, employee.resource_id, lunch=False,
        ).get(employee.resource_id.id)
        return bool(intervals)

    def _generate_for_employee_date(self, employee, target_date):
        if not employee.attendance_required:
            return False
        if not self._is_working_day(employee, target_date):
            return False

        existing = self.search([
            ('employee_id', '=', employee.id),
            ('date', '=', target_date),
        ], limit=1)

        attendances = self.env['hr.attendance'].search([
            ('employee_id', '=', employee.id),
            ('date', '=', target_date),
        ], order='check_in asc')

        calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id
        skip, reason = employee._should_skip_attendance_penalties(target_date)
        excused_status = employee._excused_attendance_status(target_date) if skip else False

        vals = {
            'employee_id': employee.id,
            'date': target_date,
            'calendar_id': calendar.id if calendar else False,
            'late_minutes': 0,
            'early_checkout_minutes': 0,
            'extra_minutes': 0,
            'billable_late_minutes': 0,
            'unworked_minutes': 0,
            'worked_hours': 0.0,
            'source_summary': False,
            'notes': False,
            'is_on_approved_leave': reason == 'leave',
            'is_public_holiday': reason == 'holiday',
        }

        if attendances:
            first = attendances[0]
            last = attendances[-1]
            vals.update({
                'check_in': first.check_in,
                'check_out': last.check_out,
                'late_minutes': 0 if skip else sum(attendances.mapped('late_minutes')),
                'early_checkout_minutes': 0 if skip else max(attendances.mapped('early_checkout_minutes') or [0]),
                'extra_minutes': 0 if skip else sum(attendances.mapped('extra_minutes')),
                'billable_late_minutes': 0 if skip else sum(attendances.mapped('billable_late_minutes')),
                'unworked_minutes': 0 if skip else sum(attendances.mapped('unworked_minutes')),
                'worked_hours': sum(attendances.mapped('worked_hours')),
                'source_summary': ', '.join(sorted({
                    src for src in attendances.mapped('attendance_source') if src
                })),
            })
            if skip:
                vals['status'] = excused_status
            else:
                statuses = attendances.mapped('attendance_status')
                open_active = any(
                    not att.check_out and att._defer_penalties_until_checkout()
                    for att in attendances
                )
                if open_active and len(attendances) == 1:
                    vals['status'] = 'present'
                elif 'incomplete' in statuses or any(not att.check_out for att in attendances):
                    vals['status'] = 'incomplete'
                elif 'late' in statuses:
                    vals['status'] = 'late'
                elif 'early_leave' in statuses:
                    vals['status'] = 'early_leave'
                else:
                    vals['status'] = 'present'
        elif skip:
            vals.update({
                'status': excused_status,
                'check_in': False,
                'check_out': False,
            })
        else:
            vals.update({
                'status': 'absent',
                'check_in': False,
                'check_out': False,
            })

        if existing:
            existing.write(vals)
            return existing
        return self.create(vals)

    @api.model
    def _cron_generate_daily_status(self, target_date=None):
        if target_date is None:
            target_date = fields.Date.today() - timedelta(days=1)
        employees = self.env['hr.employee'].search([
            ('attendance_required', '=', True),
            ('active', '=', True),
        ])
        for employee in employees:
            self._generate_for_employee_date(employee, target_date)
        return True

    @api.model
    def _cron_backfill_current_month_unworked_time(self):
        """Keep current-month unworked metrics accurate for HR reporting."""
        today = fields.Date.today()
        month_start = today.replace(day=1)

        Attendance = self.env['hr.attendance'].sudo()
        attendances = Attendance.search([
            ('date', '>=', month_start),
            ('date', '<=', today),
        ])
        if attendances:
            attendances._compute_attendance_status_fields()

        employees = self.env['hr.employee'].sudo().search([
            ('attendance_required', '=', True),
            ('active', '=', True),
        ])
        target_date = month_start
        while target_date <= today:
            for employee in employees:
                self._generate_for_employee_date(employee, target_date)
            target_date += timedelta(days=1)
        return True

    @api.model
    def _sum_unworked_minutes(self, employee, date_from, date_to):
        domain = [
            ('employee_id', '=', employee.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ]
        grouped = self.read_group(domain, ['unworked_minutes:sum'], [])
        return int((grouped[0].get('unworked_minutes_sum') if grouped else 0) or 0)

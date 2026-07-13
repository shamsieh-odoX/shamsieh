# -*- coding: utf-8 -*-

from datetime import datetime, time

import pytz
from pytz import timezone, utc

from odoo import fields, models


class AttendanceCalendarMixin(models.AbstractModel):
    _name = 'attendance.calendar.mixin'
    _description = 'Helpers for calendar-based attendance calculations'

    def _get_attendance_calendar(self):
        self.ensure_one()
        return self.resource_calendar_id or self.company_id.resource_calendar_id

    def _get_work_day_bounds(self, target_date):
        """Return scheduled (start, end) datetimes in UTC-naive for *target_date*.

        Uses resource.calendar attendance lines — never hardcoded clock times.
        Returns (False, False) on non-working days.
        """
        self.ensure_one()
        calendar = self._get_attendance_calendar()
        if not calendar:
            return False, False

        tz_name = self._get_tz()
        tz = timezone(tz_name)
        day_start = tz.localize(datetime.combine(target_date, time.min))
        day_end = tz.localize(datetime.combine(target_date, time.max))

        intervals = calendar._attendance_intervals_batch(
            day_start, day_end, self.resource_id, lunch=False,
        ).get(self.resource_id.id)
        if not intervals:
            return False, False

        starts = []
        ends = []
        for start, end, _att in intervals:
            starts.append(start)
            ends.append(end)

        scheduled_start = min(starts).astimezone(utc).replace(tzinfo=None)
        scheduled_end = max(ends).astimezone(utc).replace(tzinfo=None)
        return scheduled_start, scheduled_end

    def _datetime_to_employee_local(self, dt):
        self.ensure_one()
        if not dt:
            return False
        tz = timezone(self._get_tz())
        if dt.tzinfo:
            return dt.astimezone(tz).replace(tzinfo=None)
        return utc.localize(dt).astimezone(tz).replace(tzinfo=None)

    def _get_schedule_location_type(self, check_datetime=False, target_date=False):
        """Return schedule line location_type for the employee at check time.

        Selection priority:
        1) interval matching local check time
        2) earliest interval for the day
        """
        self.ensure_one()
        calendar = self._get_attendance_calendar()
        if not calendar:
            return False

        tz = timezone(self._get_tz())
        if check_datetime:
            if check_datetime.tzinfo:
                local_dt = check_datetime.astimezone(tz)
            else:
                local_dt = utc.localize(check_datetime).astimezone(tz)
        else:
            local_dt = fields.Datetime.now().replace(tzinfo=utc).astimezone(tz)

        if target_date:
            local_dt = tz.localize(datetime.combine(target_date, local_dt.timetz().replace(tzinfo=None)))

        day_start = tz.localize(datetime.combine(local_dt.date(), time.min))
        day_end = tz.localize(datetime.combine(local_dt.date(), time.max))
        intervals = calendar._attendance_intervals_batch(
            day_start,
            day_end,
            self.resource_id,
            lunch=False,
        ).get(self.resource_id.id)
        if not intervals:
            return False

        for start, end, attendance in sorted(intervals, key=lambda item: item[0]):
            if start <= local_dt <= end:
                return attendance.location_type or False

        _start, _end, attendance = sorted(intervals, key=lambda item: item[0])[0]
        return attendance.location_type or False

    def _get_day_datetime_bounds(self, target_date):
        """Return local start/end-of-day datetimes as UTC-naive for *target_date*."""
        self.ensure_one()
        calendar = self._get_attendance_calendar()
        tz_name = (calendar.tz if calendar else None) or self._get_tz() or 'UTC'
        tz = timezone(tz_name)
        day_start = tz.localize(datetime.combine(target_date, time.min))
        day_end = tz.localize(datetime.combine(target_date, time.max))
        return (
            day_start.astimezone(utc).replace(tzinfo=None),
            day_end.astimezone(utc).replace(tzinfo=None),
        )

    def _is_on_approved_leave(self, target_date):
        """True when the employee has a validated leave covering *target_date*."""
        self.ensure_one()
        if 'hr.leave' not in self.env:
            return False
        day_start, day_end = self._get_day_datetime_bounds(target_date)
        return bool(self.env['hr.leave'].sudo().search([
            ('employee_id', '=', self.id),
            ('state', '=', 'validate'),
            ('date_from', '<=', day_end),
            ('date_to', '>=', day_start),
        ], limit=1))

    def _is_public_holiday(self, target_date):
        """True when *target_date* is a company or calendar public holiday."""
        self.ensure_one()
        company = self.company_id
        day_start, day_end = self._get_day_datetime_bounds(target_date)

        calendar_ids = {False}
        calendar = self._get_attendance_calendar()
        if calendar:
            calendar_ids.add(calendar.id)
        if company and company.resource_calendar_id:
            calendar_ids.add(company.resource_calendar_id.id)

        Leave = self.env['resource.calendar.leaves'].sudo()
        company_holiday = Leave.search([
            ('resource_id', '=', False),
            ('time_type', '=', 'leave'),
            ('date_from', '<=', day_end),
            ('date_to', '>=', day_start),
            '|', ('company_id', '=', False), ('company_id', '=', company.id if company else False),
            ('calendar_id', 'in', list(calendar_ids)),
        ], limit=1)
        if company_holiday:
            return True

        if not calendar:
            return False

        tz_name = calendar.tz or self._get_tz() or 'UTC'
        tz = timezone(tz_name)
        local_day_start = tz.localize(datetime.combine(target_date, time.min))
        local_day_end = tz.localize(datetime.combine(target_date, time.max))
        intervals = calendar._leave_intervals(
            local_day_start,
            local_day_end,
            resource=self.resource_id,
            domain=[('time_type', '=', 'leave')],
            tz=tz,
        )
        return bool(intervals)

    def _should_skip_attendance_penalties(self, target_date):
        """Return (skip, reason) where reason is 'leave', 'holiday', or False."""
        self.ensure_one()
        if self._is_on_approved_leave(target_date):
            return True, 'leave'
        if self._is_public_holiday(target_date):
            return True, 'holiday'
        return False, False

    def _excused_attendance_status(self, target_date):
        """Return daily/attendance status when penalties are skipped, or False."""
        self.ensure_one()
        skip, reason = self._should_skip_attendance_penalties(target_date)
        if not skip:
            return False
        return 'on_holiday' if reason == 'holiday' else 'on_leave'

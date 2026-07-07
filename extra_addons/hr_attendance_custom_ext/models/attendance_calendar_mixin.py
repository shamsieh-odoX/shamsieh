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

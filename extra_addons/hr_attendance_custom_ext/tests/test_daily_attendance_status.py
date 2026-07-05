# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from odoo.tests.common import TransactionCase


class TestDailyAttendanceStatus(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'Daily Status Calendar',
            'tz': 'UTC',
            'attendance_ids': [
                (0, 0, {'name': 'Mon', 'dayofweek': '0', 'hour_from': 8, 'hour_to': 16, 'day_period': 'morning'}),
            ],
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Daily Status Employee',
            'resource_calendar_id': cls.calendar.id,
            'attendance_required': True,
        })
        cls.Status = cls.env['hr.attendance.daily.status']

    def test_workday_without_attendance_is_absent(self):
        monday = datetime(2026, 6, 1).date()
        record = self.Status._generate_for_employee_date(self.employee, monday)
        self.assertTrue(record)
        self.assertEqual(record.status, 'absent')

    def test_workday_with_attendance_is_present(self):
        monday = datetime(2026, 6, 8, 8, 0, 0)
        self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': monday,
            'check_out': monday + timedelta(hours=8),
            'attendance_source': 'fingerprint',
        })
        record = self.Status._generate_for_employee_date(self.employee, monday.date())
        self.assertEqual(record.status, 'present')
        self.assertTrue(record.check_in)

    def test_weekend_skipped(self):
        saturday = datetime(2026, 6, 6).date()
        record = self.Status._generate_for_employee_date(self.employee, saturday)
        self.assertFalse(record)

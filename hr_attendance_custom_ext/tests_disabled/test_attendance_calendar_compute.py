# -*- coding: utf-8 -*-

from datetime import datetime

from odoo.tests.common import TransactionCase


class TestAttendanceCalendarCompute(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'Test 8h Calendar',
            'tz': 'UTC',
            'attendance_ids': [
                (0, 0, {'name': 'Mon AM', 'dayofweek': '0', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'name': 'Mon Lunch', 'dayofweek': '0', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'}),
                (0, 0, {'name': 'Mon PM', 'dayofweek': '0', 'hour_from': 13, 'hour_to': 16, 'day_period': 'afternoon'}),
            ],
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Calendar Test Employee',
            'resource_calendar_id': cls.calendar.id,
        })

    def test_late_minutes_from_calendar(self):
        policy = self.env['fingerprint.attendance.policy'].get_company_default(
            self.employee.company_id,
        )
        policy.late_grace_minutes = 0
        monday = datetime(2026, 6, 1, 8, 30, 0)
        attendance = self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': monday,
            'check_out': datetime(2026, 6, 1, 16, 0, 0),
            'attendance_source': 'manual',
        })
        self.assertEqual(attendance.late_minutes, 30)
        self.assertEqual(attendance.extra_minutes, 0)
        self.assertEqual(attendance.billable_late_minutes, 30)
        self.assertEqual(attendance.unworked_minutes, 30)
        self.assertEqual(attendance.attendance_status, 'late')

    def test_on_time_attendance(self):
        monday = datetime(2026, 6, 1, 8, 0, 0)
        attendance = self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': monday,
            'check_out': datetime(2026, 6, 1, 16, 0, 0),
            'attendance_source': 'manual',
        })
        self.assertEqual(attendance.late_minutes, 0)
        self.assertEqual(attendance.unworked_minutes, 0)
        self.assertEqual(attendance.attendance_status, 'present')

    def test_late_grace_from_policy(self):
        policy = self.env['fingerprint.attendance.policy'].get_company_default(
            self.employee.company_id,
        )
        policy.late_grace_minutes = 15
        monday = datetime(2026, 6, 1, 8, 10, 0)
        attendance = self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': monday,
            'check_out': datetime(2026, 6, 1, 16, 0, 0),
            'attendance_source': 'manual',
        })
        self.assertEqual(attendance.late_minutes, 0)
        self.assertEqual(attendance.billable_late_minutes, 0)
        self.assertEqual(attendance.unworked_minutes, 0)
        self.assertEqual(attendance.attendance_status, 'present')

    def test_late_is_fully_compensated_by_extra_minutes(self):
        policy = self.env['fingerprint.attendance.policy'].get_company_default(
            self.employee.company_id,
        )
        policy.late_grace_minutes = 0
        check_in = datetime(2026, 6, 1, 8, 25, 0)
        attendance = self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': check_in,
            'check_out': datetime(2026, 6, 1, 16, 25, 0),
            'attendance_source': 'manual',
        })
        self.assertEqual(attendance.late_minutes, 25)
        self.assertEqual(attendance.extra_minutes, 25)
        self.assertEqual(attendance.billable_late_minutes, 0)
        self.assertEqual(attendance.unworked_minutes, 0)
        self.assertEqual(attendance.attendance_status, 'present')

    def test_late_is_partially_compensated_by_extra_minutes(self):
        policy = self.env['fingerprint.attendance.policy'].get_company_default(
            self.employee.company_id,
        )
        policy.late_grace_minutes = 0
        attendance = self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': datetime(2026, 6, 1, 8, 25, 0),
            'check_out': datetime(2026, 6, 1, 16, 10, 0),
            'attendance_source': 'manual',
        })
        self.assertEqual(attendance.late_minutes, 25)
        self.assertEqual(attendance.extra_minutes, 10)
        self.assertEqual(attendance.billable_late_minutes, 15)
        self.assertEqual(attendance.unworked_minutes, 15)
        self.assertEqual(attendance.attendance_status, 'late')

    def test_early_leave_counts_as_unworked_minutes(self):
        policy = self.env['fingerprint.attendance.policy'].get_company_default(
            self.employee.company_id,
        )
        policy.early_checkout_grace_minutes = 0
        attendance = self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': datetime(2026, 6, 1, 8, 0, 0),
            'check_out': datetime(2026, 6, 1, 15, 20, 0),
            'attendance_source': 'manual',
        })
        self.assertEqual(attendance.early_checkout_minutes, 40)
        self.assertEqual(attendance.unworked_minutes, 40)
        self.assertEqual(attendance.attendance_status, 'early_leave')

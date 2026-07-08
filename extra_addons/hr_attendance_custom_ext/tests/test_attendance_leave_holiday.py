# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from odoo.tests.common import TransactionCase


class TestAttendanceLeaveHoliday(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'Leave Holiday Calendar',
            'tz': 'UTC',
            'attendance_ids': [
                (0, 0, {
                    'name': 'Mon',
                    'dayofweek': '0',
                    'hour_from': 8,
                    'hour_to': 16,
                    'day_period': 'morning',
                }),
            ],
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Leave Holiday Employee',
            'resource_calendar_id': cls.calendar.id,
            'attendance_required': True,
        })
        cls.leave_type = cls.env['hr.leave.type'].create({
            'name': 'Test Leave',
            'requires_allocation': False,
            'leave_validation_type': 'no_validation',
        })
        cls.Status = cls.env['hr.attendance.daily.status']
        cls.monday = datetime(2026, 6, 1).date()

    def _create_validated_leave(self, date_from, date_to=None):
        date_to = date_to or date_from
        return self.env['hr.leave'].create({
            'name': 'Test Leave',
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type.id,
            'request_date_from': date_from,
            'request_date_to': date_to,
        })

    def test_approved_leave_no_attendance_is_on_leave(self):
        self._create_validated_leave(self.monday)
        record = self.Status._generate_for_employee_date(self.employee, self.monday)
        self.assertTrue(record)
        self.assertEqual(record.status, 'on_leave')
        self.assertNotEqual(record.status, 'absent')

    def test_approved_leave_late_checkin_not_marked_late(self):
        self._create_validated_leave(self.monday)
        monday_dt = datetime(2026, 6, 1, 8, 30, 0)
        attendance = self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': monday_dt,
            'check_out': monday_dt + timedelta(hours=8),
            'attendance_source': 'manual',
        })
        self.assertEqual(attendance.late_minutes, 0)
        self.assertEqual(attendance.attendance_status, 'on_leave')
        record = self.Status.search([
            ('employee_id', '=', self.employee.id),
            ('date', '=', self.monday),
        ], limit=1)
        self.assertTrue(record)
        self.assertEqual(record.status, 'on_leave')
        self.assertEqual(record.late_minutes, 0)

    def test_public_holiday_no_attendance_is_on_leave(self):
        self.env['resource.calendar.leaves'].sudo().create({
            'name': 'Test Public Holiday',
            'calendar_id': self.calendar.id,
            'date_from': datetime(2026, 6, 1, 0, 0, 0),
            'date_to': datetime(2026, 6, 1, 23, 59, 59),
        })
        record = self.Status._generate_for_employee_date(self.employee, self.monday)
        self.assertTrue(record)
        self.assertEqual(record.status, 'on_leave')
        self.assertNotEqual(record.status, 'absent')

    def test_normal_workday_unaffected(self):
        monday_dt = datetime(2026, 6, 1, 8, 0, 0)
        attendance = self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': monday_dt,
            'check_out': monday_dt + timedelta(hours=8),
            'attendance_source': 'manual',
        })
        self.assertEqual(attendance.late_minutes, 0)
        self.assertEqual(attendance.attendance_status, 'present')
        record = self.Status.search([
            ('employee_id', '=', self.employee.id),
            ('date', '=', self.monday),
        ], limit=1)
        self.assertTrue(record)
        self.assertEqual(record.status, 'present')
        self.assertEqual(record.late_minutes, 0)

# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'hr_attendance_custom_ext')
class TestRemoteWorkRequest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.face_attendance_stub_enabled = True

        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'Remote Work Test Calendar',
            'tz': 'UTC',
            'attendance_ids': [
                (0, 0, {
                    'name': day_name,
                    'dayofweek': str(day),
                    'hour_from': 8,
                    'hour_to': 16,
                    'day_period': 'morning',
                    'location_type': 'office',
                })
                for day, day_name in enumerate(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'])
            ],
        })
        cls.leave_type = cls.env.ref('hr_attendance_custom_ext.leave_type_remote_work')
        cls.Leave = cls.env['hr.leave']

        cls.employee = cls.env['hr.employee'].create({
            'name': 'Remote Work Employee',
            'company_id': cls.company.id,
            'resource_calendar_id': cls.calendar.id,
            'remote_attendance_allowed': True,
        })

    def _create_remote_leave(self, date_from, date_to=None):
        return self.Leave.create({
            'name': 'Remote Work Test',
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type.id,
            'request_date_from': date_from,
            'request_date_to': date_to or date_from,
        })

    def test_approved_remote_leave_overrides_office_schedule(self):
        today = fields.Date.context_today(self.employee)
        leave = self._create_remote_leave(today)
        self.assertEqual(leave.state, 'validate')
        self.assertEqual(self.employee._get_attendance_scheduled_location(), 'home')
        self.assertEqual(self.employee._get_effective_work_location_type(), 'home')
        self.assertTrue(self.employee._manual_attendance_allowed())

    def test_pending_remote_leave_does_not_allow_manual_check_in(self):
        today = fields.Date.context_today(self.employee)
        pending_type = self.env['hr.leave.type'].create({
            'name': 'Pending Remote Work',
            'requires_allocation': False,
            'leave_validation_type': 'manager',
        })
        self.Leave.create({
            'name': 'Pending Remote Work',
            'employee_id': self.employee.id,
            'holiday_status_id': pending_type.id,
            'request_date_from': today,
            'request_date_to': today,
        })
        self.assertEqual(self.employee._get_attendance_scheduled_location(), 'office')
        with self.assertRaises(UserError):
            self.employee._raise_if_manual_attendance_blocked()

    def test_period_remote_leave_covers_each_day(self):
        today = fields.Date.context_today(self.employee)
        self._create_remote_leave(today, today + timedelta(days=2))
        self.assertTrue(self.employee._has_approved_remote_work())
        self.assertTrue(self.employee._has_approved_remote_work(fields.Datetime.now() + timedelta(days=1)))
        self.assertEqual(self.employee._get_attendance_scheduled_location(), 'home')

    def test_systray_flags_face_when_enrolled(self):
        today = fields.Date.context_today(self.employee)
        self._create_remote_leave(today)
        self.env['hr.employee.face.template'].create({
            'employee_id': self.employee.id,
            'active': True,
            'provider': 'insightface',
            'embedding_json': '[0.1, 0.2]',
        })
        data = self.employee._get_attendance_systray_user_data()
        self.assertTrue(data['manual_attendance_allowed'])
        self.assertTrue(data['approved_remote_work_today'])
        self.assertTrue(data['check_in_requires_face'])
        self.assertFalse(data['check_in_requires_home_pin'])

    def test_systray_flags_home_pin_without_face(self):
        today = fields.Date.context_today(self.employee)
        self._create_remote_leave(today)
        self.employee._set_home_attendance_pin('2468')
        data = self.employee._get_attendance_systray_user_data()
        self.assertTrue(data['manual_attendance_allowed'])
        self.assertFalse(data['check_in_requires_face'])
        self.assertTrue(data['check_in_requires_home_pin'])

# -*- coding: utf-8 -*-

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestWorkLocationCheckIn(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'office_geo_latitude': 31.9500,
            'office_geo_longitude': 35.9100,
            'office_geo_radius_meters': 100,
            'face_attendance_stub_enabled': True,
        })
        cls.home_location = cls.env.ref('hr.home_work_location')
        cls.office_location = cls.env.ref('hr.home_work_office')
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'Location Rules Calendar',
            'tz': 'UTC',
            'attendance_ids': [
                (0, 0, {'name': 'Mon', 'dayofweek': '0', 'hour_from': 8, 'hour_to': 16, 'day_period': 'morning', 'location_type': 'office'}),
                (0, 0, {'name': 'Tue', 'dayofweek': '1', 'hour_from': 8, 'hour_to': 16, 'day_period': 'morning', 'location_type': 'office'}),
                (0, 0, {'name': 'Wed', 'dayofweek': '2', 'hour_from': 8, 'hour_to': 16, 'day_period': 'morning', 'location_type': 'office'}),
                (0, 0, {'name': 'Thu', 'dayofweek': '3', 'hour_from': 8, 'hour_to': 16, 'day_period': 'morning', 'location_type': 'office'}),
                (0, 0, {'name': 'Fri', 'dayofweek': '4', 'hour_from': 8, 'hour_to': 16, 'day_period': 'morning', 'location_type': 'office'}),
                (0, 0, {'name': 'Sat', 'dayofweek': '5', 'hour_from': 8, 'hour_to': 16, 'day_period': 'morning', 'location_type': 'office'}),
                (0, 0, {'name': 'Sun', 'dayofweek': '6', 'hour_from': 8, 'hour_to': 16, 'day_period': 'morning', 'location_type': 'office'}),
            ],
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Location Rules Employee',
            'company_id': cls.company.id,
            'resource_calendar_id': cls.calendar.id,
        })

    def _set_today_schedule_location(self, location_type):
        dayofweek = str(fields.Date.context_today(self.employee).weekday())
        lines = self.employee.resource_calendar_id.attendance_ids.filtered(
            lambda line: line.dayofweek == dayofweek
        )
        lines.write({'location_type': location_type})

    def test_home_requires_face_or_pin_for_systray_check_in(self):
        self._set_today_schedule_location('home')
        with self.assertRaises(UserError):
            self.employee._attendance_action_change()

    def test_home_face_check_in_allowed_with_stub(self):
        self._set_today_schedule_location('home')
        self.employee.remote_attendance_allowed = True
        log = self.env['face.attendance.log'].create_face_check(
            employee=self.employee,
            action_type='check_in',
        )
        self.assertEqual(log.verification_status, 'passed')
        self.assertTrue(log.attendance_id)

    def test_home_face_check_in_blocked_when_remote_face_disabled(self):
        self._set_today_schedule_location('home')
        self.employee.remote_attendance_allowed = False
        with self.assertRaises(UserError):
            self.env['face.attendance.log'].create_face_check(
                employee=self.employee,
                action_type='check_in',
            )

    def test_home_pin_check_in_allowed(self):
        self._set_today_schedule_location('home')
        self.employee._set_home_attendance_pin('1234')
        self.assertTrue(self.employee._verify_home_attendance_pin('1234'))
        attendance = self.employee.with_context(
            attendance_via_home_pin=True,
        )._attendance_action_change()
        self.assertTrue(attendance.check_in)

    def test_home_invalid_pin_rejected(self):
        self.employee._set_home_attendance_pin('1234')
        self.assertFalse(self.employee._verify_home_attendance_pin('9999'))

    def test_office_requires_device_location(self):
        self._set_today_schedule_location('office')
        with self.assertRaises(UserError):
            self.employee.with_context(
                attendance_device_location=False,
            )._attendance_action_change({
                'latitude': 31.95,
                'longitude': 35.91,
                'mode': 'systray',
            })

    def test_office_check_in_inside_radius(self):
        self._set_today_schedule_location('office')
        attendance = self.employee.with_context(
            attendance_device_location=True,
        )._attendance_action_change({
            'latitude': 31.9501,
            'longitude': 35.9101,
            'mode': 'systray',
        })
        self.assertTrue(attendance.check_in)

    def test_office_check_in_outside_radius_blocked(self):
        self._set_today_schedule_location('office')
        with self.assertRaises(UserError):
            self.employee.with_context(
                attendance_device_location=True,
            )._attendance_action_change({
                'latitude': 32.0,
                'longitude': 36.0,
                'mode': 'systray',
            })

    def test_office_face_check_in_blocked(self):
        self._set_today_schedule_location('office')
        log = self.env['face.attendance.log'].create_face_check(
            employee=self.employee,
            action_type='check_in',
        )
        self.assertEqual(log.verification_status, 'failed')
        self.assertIn('geolocation', log.error_message.lower())

    def test_single_daily_check_in_enforced(self):
        self._set_today_schedule_location('office')
        self.employee.with_context(
            attendance_device_location=True,
        )._attendance_action_change({
            'latitude': 31.9501,
            'longitude': 35.9101,
            'mode': 'systray',
        })
        self.employee._attendance_action_change({
            'latitude': 31.9501,
            'longitude': 35.9101,
            'mode': 'systray',
        })
        self.employee.invalidate_recordset(['attendance_state'])
        with self.assertRaises(UserError):
            self.employee.with_context(
                attendance_device_location=True,
            )._attendance_action_change({
                'latitude': 31.9501,
                'longitude': 35.9101,
                'mode': 'systray',
            })

    def test_effective_work_location_uses_schedule_line(self):
        self._set_today_schedule_location('home')
        self.assertEqual(self.employee._get_effective_work_location_type(), 'home')

    def test_effective_work_location_fallback_to_work_location(self):
        calendar = self.env['resource.calendar'].create({
            'name': 'Fallback Calendar',
            'tz': 'UTC',
            'attendance_ids': [
                (0, 0, {'name': 'Mon', 'dayofweek': '0', 'hour_from': 8, 'hour_to': 16, 'day_period': 'morning', 'location_type': 'office'}),
            ],
        })
        employee = self.env['hr.employee'].create({
            'name': 'Fallback Employee',
            'company_id': self.company.id,
            'resource_calendar_id': calendar.id,
        })
        # Force fallback by keeping today without any schedule intervals.
        employee.work_location_id = self.home_location
        self.assertEqual(employee._get_effective_work_location_type(), 'home')

    def test_work_location_id_still_supported(self):
        self.employee.work_location_id = self.home_location
        self.assertEqual(self.employee._get_effective_work_location_type(), 'home')

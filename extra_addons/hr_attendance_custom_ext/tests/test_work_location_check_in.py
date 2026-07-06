# -*- coding: utf-8 -*-

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
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Location Rules Employee',
            'company_id': cls.company.id,
        })

    def test_home_requires_face_for_systray_check_in(self):
        self.employee.work_location_id = self.home_location
        with self.assertRaises(UserError):
            self.employee._attendance_action_change()

    def test_home_face_check_in_allowed_with_stub(self):
        self.employee.work_location_id = self.home_location
        log = self.env['face.attendance.log'].create_face_check(
            employee=self.employee,
            action_type='check_in',
        )
        self.assertEqual(log.verification_status, 'passed')
        self.assertTrue(log.attendance_id)

    def test_office_requires_device_location(self):
        self.employee.work_location_id = self.office_location
        with self.assertRaises(UserError):
            self.employee.with_context(
                attendance_device_location=False,
            )._attendance_action_change({
                'latitude': 31.95,
                'longitude': 35.91,
                'mode': 'systray',
            })

    def test_office_check_in_inside_radius(self):
        self.employee.work_location_id = self.office_location
        attendance = self.employee.with_context(
            attendance_device_location=True,
        )._attendance_action_change({
            'latitude': 31.9501,
            'longitude': 35.9101,
            'mode': 'systray',
        })
        self.assertTrue(attendance.check_in)

    def test_office_check_in_outside_radius_blocked(self):
        self.employee.work_location_id = self.office_location
        with self.assertRaises(UserError):
            self.employee.with_context(
                attendance_device_location=True,
            )._attendance_action_change({
                'latitude': 32.0,
                'longitude': 36.0,
                'mode': 'systray',
            })

    def test_office_face_check_in_blocked(self):
        self.employee.work_location_id = self.office_location
        log = self.env['face.attendance.log'].create_face_check(
            employee=self.employee,
            action_type='check_in',
        )
        self.assertEqual(log.verification_status, 'failed')
        self.assertIn('geolocation', log.error_message.lower())

    def test_single_daily_check_in_enforced(self):
        self.employee.work_location_id = self.office_location
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

    def test_effective_work_location_uses_work_location_id(self):
        self.employee.work_location_id = self.home_location
        self.assertEqual(self.employee._get_effective_work_location_type(), 'home')

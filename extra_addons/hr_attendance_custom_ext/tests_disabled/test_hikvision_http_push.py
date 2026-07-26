# -*- coding: utf-8 -*-

from odoo import fields
from odoo.tests.common import TransactionCase

from odoo.addons.hr_attendance_custom_ext.services.hikvision_http_push import (
    classify_http_push,
    process_http_push,
)


class TestHikvisionHttpPush(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({
            'name': 'HTTP Push Employee',
            'barcode': '5',
            'biometric_device_user_id': '5',
        })
        cls.device = cls.env['fingerprint.device'].create({
            'name': 'HTTP Push Device',
            'api_type': 'hikvision',
            'device_ip': '192.168.100.85',
            'username': 'admin',
            'password': 'test',
            'http_listening_enabled': True,
        })

    def test_classify_break_in(self):
        action, reason = classify_http_push({
            'employeeNoString': '5',
            'attendanceStatus': 'breakIn',
            'dateTime': '2026-07-13T08:00:00+03:00',
            'serialNo': 1001,
            'subEventType': 38,
        })
        self.assertEqual(action, 'process')
        self.assertEqual(reason, 'break_in')

    def test_classify_door_event_ignored(self):
        action, reason = classify_http_push({
            'subEventType': 21,
            'dateTime': '2026-07-13T08:00:00+03:00',
        })
        self.assertEqual(action, 'ignored')

    def test_process_check_in_creates_attendance(self):
        result = process_http_push(self.device, {
            'employeeNoString': '5',
            'attendanceStatus': 'checkIn',
            'dateTime': '2026-07-13T08:00:00+03:00',
            'serialNo': 1002,
            'subEventType': 38,
        })
        self.assertEqual(result['status'], 'created')
        attendance = self.env['hr.attendance'].browse(result['attendance_id'])
        self.assertTrue(attendance.check_in)
        self.assertEqual(attendance.attendance_source, 'fingerprint')

    def test_process_break_does_not_close_attendance(self):
        process_http_push(self.device, {
            'employeeNoString': '5',
            'attendanceStatus': 'checkIn',
            'dateTime': '2026-07-13T08:00:00+03:00',
            'serialNo': 1003,
            'subEventType': 38,
        })
        result = process_http_push(self.device, {
            'employeeNoString': '5',
            'attendanceStatus': 'breakOut',
            'dateTime': '2026-07-13T10:00:00+03:00',
            'serialNo': 1004,
            'subEventType': 38,
        })
        self.assertEqual(result['status'], 'break_started')
        attendance = self.env['hr.attendance'].search([
            ('employee_id', '=', self.employee.id),
            ('check_out', '=', False),
        ], limit=1)
        self.assertTrue(attendance)
        self.assertEqual(self.employee.hikvision_presence_status, 'on_break')
        end_result = process_http_push(self.device, {
            'employeeNoString': '5',
            'attendanceStatus': 'breakIn',
            'dateTime': '2026-07-13T10:30:00+03:00',
            'serialNo': 1005,
            'subEventType': 38,
        })
        self.assertEqual(end_result['status'], 'break_ended')
        self.assertEqual(self.employee.hikvision_presence_status, 'working')

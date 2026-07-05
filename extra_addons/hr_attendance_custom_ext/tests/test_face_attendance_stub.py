# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase


class TestFaceAttendanceStub(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'face_attendance_stub_enabled': True})
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Remote Face Employee',
            'remote_attendance_allowed': True,
            'company_id': cls.company.id,
        })

    def test_face_check_creates_attendance(self):
        Log = self.env['face.attendance.log']
        log = Log.create_face_check(
            employee=self.employee,
            action_type='check_in',
        )
        self.assertEqual(log.verification_status, 'passed')
        self.assertTrue(log.attendance_id)
        self.assertEqual(log.attendance_id.attendance_source, 'face')
        self.assertTrue(log.attendance_id.face_verified)

    def test_face_check_blocked_without_permission(self):
        self.employee.remote_attendance_allowed = False
        Log = self.env['face.attendance.log']
        with self.assertRaises(Exception):
            Log.create_face_check(
                employee=self.employee,
                action_type='check_in',
            )

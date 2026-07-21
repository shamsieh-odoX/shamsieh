# -*- coding: utf-8 -*-

from datetime import datetime

from odoo.tests.common import TransactionCase


class TestFingerprintProcess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Process Test Employee',
            'biometric_device_user_id': 'PROC001',
        })
        cls.device = cls.env['fingerprint.device'].create({
            'name': 'Process Test Device',
            'api_type': 'file_import',
        })
        cls.Log = cls.env['fingerprint.device.log']

    def _create_log(self, external_id, event_time, device_user_id='PROC001', employee=None):
        return self.Log.create({
            'device_id': self.device.id,
            'external_id': external_id,
            'device_user_id': device_user_id,
            'employee_id': employee.id if employee else False,
            'event_time': event_time,
            'state': 'draft',
        })

    def test_one_event_creates_check_in_only(self):
        log = self._create_log('ONE001', datetime(2026, 6, 2, 8, 0, 0))
        log._process_pending_logs()
        self.assertEqual(log.state, 'processed')
        attendance = log.attendance_id
        self.assertTrue(attendance)
        self.assertEqual(attendance.check_in, datetime(2026, 6, 2, 8, 0, 0))
        self.assertFalse(attendance.check_out)
        self.assertEqual(attendance.attendance_source, 'fingerprint')
        self.assertFalse(attendance.face_verified)

    def test_second_event_same_day_updates_check_out(self):
        log1 = self._create_log('TWO001', datetime(2026, 6, 3, 8, 0, 0))
        log2 = self._create_log('TWO002', datetime(2026, 6, 3, 16, 0, 0))
        (log1 | log2)._process_pending_logs()
        self.assertEqual(log1.state, 'processed')
        self.assertEqual(log2.state, 'processed')
        self.assertEqual(log1.attendance_id, log2.attendance_id)
        attendance = log1.attendance_id
        self.assertEqual(attendance.check_in, datetime(2026, 6, 3, 8, 0, 0))
        self.assertEqual(attendance.check_out, datetime(2026, 6, 3, 16, 0, 0))

    def test_duplicate_event_does_not_duplicate_attendance(self):
        log = self._create_log('DUP001', datetime(2026, 6, 4, 8, 0, 0))
        existing = self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': datetime(2026, 6, 4, 8, 0, 0),
            'attendance_source': 'fingerprint',
            'device_id': self.device.id,
            'device_user_id': 'PROC001',
            'external_log_id': 'DUP001',
            'face_verified': False,
            'in_mode': 'technical',
        })
        log._process_pending_logs()
        self.assertEqual(log.state, 'duplicate')
        self.assertEqual(log.attendance_id, existing)
        self.assertEqual(self.env['hr.attendance'].search_count([
            ('employee_id', '=', self.employee.id),
            ('date', '=', datetime(2026, 6, 4).date()),
        ]), 1)

    def test_unmapped_employee_becomes_error(self):
        log = self._create_log(
            'ERR001',
            datetime(2026, 6, 5, 8, 0, 0),
            device_user_id='UNKNOWN',
        )
        log._process_pending_logs()
        self.assertEqual(log.state, 'error')
        self.assertEqual(log.error_message, 'No employee mapped for device user ID')
        self.assertFalse(log.attendance_id)

    def test_logs_link_to_attendance_id(self):
        log1 = self._create_log('LINK001', datetime(2026, 6, 6, 8, 0, 0))
        log2 = self._create_log('LINK002', datetime(2026, 6, 6, 17, 0, 0))
        (log1 | log2)._process_pending_logs()
        self.assertTrue(log1.attendance_id)
        self.assertEqual(log1.attendance_id, log2.attendance_id)
        self.assertEqual(log1.attendance_id.device_id, self.device)
        self.assertEqual(log1.attendance_id.external_log_id, 'LINK001')

    def test_reset_to_draft_clears_error(self):
        log = self._create_log(
            'RST001',
            datetime(2026, 6, 7, 8, 0, 0),
            device_user_id='UNKNOWN',
        )
        log._process_pending_logs()
        self.assertEqual(log.state, 'error')
        log.action_reset_to_draft()
        self.assertEqual(log.state, 'draft')
        self.assertFalse(log.error_message)

    def test_employee_biometric_id_relinks_error_log(self):
        employee = self.env['hr.employee'].create({'name': 'Relink Employee'})
        log = self._create_log(
            'REL001',
            datetime(2026, 6, 8, 8, 0, 0),
            device_user_id='REL002',
        )
        log._process_pending_logs()
        self.assertEqual(log.state, 'error')
        employee.write({'biometric_device_user_id': 'REL002'})
        self.assertEqual(log.employee_id, employee)
        self.assertEqual(log.state, 'draft')

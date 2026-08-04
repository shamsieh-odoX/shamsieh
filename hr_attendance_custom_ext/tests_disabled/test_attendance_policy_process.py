# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from odoo.tests.common import TransactionCase


class TestAttendancePolicyProcess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Policy Employee',
            'biometric_device_user_id': 'POL001',
        })
        cls.policy = cls.env['fingerprint.attendance.policy'].get_company_default(
            cls.employee.company_id,
        )
        cls.device = cls.env['fingerprint.device'].create({
            'name': 'Policy Test Device',
            'api_type': 'file_import',
            'policy_id': cls.policy.id,
        })
        cls.Log = cls.env['fingerprint.device.log']

    def _create_log(self, external_id, event_time, device_user_id='POL001'):
        return self.Log.create({
            'device_id': self.device.id,
            'external_id': external_id,
            'device_user_id': device_user_id,
            'event_time': event_time,
            'state': 'draft',
        })

    def test_first_last_three_scans_middle_unknown(self):
        base = datetime(2026, 6, 10, 8, 0, 0)
        log1 = self._create_log('FL001', base)
        log2 = self._create_log('FL002', base + timedelta(hours=4))
        log3 = self._create_log('FL003', base + timedelta(hours=8))
        (log1 | log2 | log3)._process_pending_logs()
        self.assertEqual(log1.punch_type, 'check_in')
        self.assertEqual(log2.punch_type, 'unknown')
        self.assertEqual(log3.punch_type, 'check_out')
        self.assertEqual(log1.attendance_id, log3.attendance_id)

    def test_duplicate_scan_within_window(self):
        base = datetime(2026, 6, 11, 8, 0, 0)
        log1 = self._create_log('DUPW001', base)
        log2 = self._create_log('DUPW002', base + timedelta(minutes=1))
        (log1 | log2)._process_pending_logs()
        self.assertEqual(log1.state, 'processed')
        self.assertEqual(log2.state, 'duplicate')

    def test_checkout_gap_too_small(self):
        self.policy.minimum_checkout_gap_minutes = 30
        base = datetime(2026, 6, 12, 8, 0, 0)
        log1 = self._create_log('GAP001', base)
        log2 = self._create_log('GAP002', base + timedelta(minutes=10))
        (log1 | log2)._process_pending_logs()
        attendance = log1.attendance_id
        self.assertTrue(attendance)
        self.assertFalse(attendance.check_out)

    def test_alternating_in_out_two_scans(self):
        alt_policy = self.policy.copy({
            'name': 'Alternating',
            'is_company_default': False,
            'process_mode': 'alternating_in_out',
        })
        self.device.policy_id = alt_policy.id
        base = datetime(2026, 6, 13, 8, 0, 0)
        log1 = self._create_log('ALT001', base)
        log2 = self._create_log('ALT002', base + timedelta(hours=8))
        (log1 | log2)._process_pending_logs()
        self.assertEqual(log1.punch_type, 'check_in')
        self.assertEqual(log2.punch_type, 'check_out')
        self.assertTrue(log1.attendance_id.check_out)

    def test_policy_fallback_company_default(self):
        self.device.policy_id = False
        log = self._create_log('DEF001', datetime(2026, 6, 14, 8, 0, 0))
        log._process_pending_logs()
        self.assertEqual(log.state, 'processed')

    def test_unmapped_becomes_error(self):
        log = self._create_log(
            'ERRPOL001',
            datetime(2026, 6, 15, 8, 0, 0),
            device_user_id='UNKNOWN',
        )
        log._process_pending_logs()
        self.assertEqual(log.state, 'error')

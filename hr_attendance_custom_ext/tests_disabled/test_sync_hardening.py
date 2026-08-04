# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from odoo.tests.common import TransactionCase


class TestSyncHardening(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.device = cls.env['fingerprint.device'].create({
            'name': 'Hardening Device',
            'api_type': 'file_import',
            'sync_lookback_hours': 48,
            'last_sync_checkpoint': datetime(2026, 6, 1, 12, 0, 0),
        })

    def test_checkpoint_narrows_sync_window(self):
        date_to = datetime(2026, 6, 3, 12, 0, 0)
        lookback_from = date_to - timedelta(hours=self.device.sync_lookback_hours)
        checkpoint = self.device.last_sync_checkpoint
        date_from = max(lookback_from, checkpoint - timedelta(minutes=5))
        self.assertEqual(date_from, max(lookback_from, checkpoint - timedelta(minutes=5)))

    def test_log_audit_fields_on_process(self):
        employee = self.env['hr.employee'].create({
            'name': 'Audit Employee',
            'biometric_device_user_id': 'AUD001',
        })
        log = self.env['fingerprint.device.log'].create({
            'device_id': self.device.id,
            'external_id': 'AUD001',
            'device_user_id': 'AUD001',
            'event_time': datetime(2026, 6, 10, 8, 0, 0),
            'state': 'draft',
        })
        log._process_pending_logs()
        self.assertEqual(log.state, 'processed')
        self.assertTrue(log.processed_at)
        self.assertEqual(log.attempt_count, 1)

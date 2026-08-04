# -*- coding: utf-8 -*-

import base64
from datetime import datetime

from odoo.tests.common import TransactionCase


class TestFingerprintSync(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Fingerprint Employee',
            'biometric_device_user_id': 'FP001',
        })
        csv_content = (
            'external_id,device_user_id,punch_time,punch_type\n'
            'EXT001,FP001,2026-06-01 08:00:00,check_in\n'
            'EXT002,FP001,2026-06-01 16:00:00,check_out\n'
        )
        cls.device = cls.env['fingerprint.device'].create({
            'name': 'Test Import Device',
            'api_type': 'file_import',
            'import_file_data': base64.b64encode(csv_content.encode()),
            'import_file_name': 'test.csv',
        })

    def test_fingerprint_log_creates_attendance(self):
        connector_logs = self.device.env['fingerprint.device.log']
        from odoo.addons.hr_attendance_custom_ext.services.hikvision_connector import HikvisionConnector
        connector = HikvisionConnector(self.device)
        logs, stats = connector.sync_device_logs()
        self.assertTrue(logs)
        self.assertEqual(stats['stored'], 2)
        processed = logs._process_pending_logs()
        self.assertTrue(processed)
        attendance = self.env['hr.attendance'].search([
            ('employee_id', '=', self.employee.id),
        ], limit=1)
        self.assertTrue(attendance)
        self.assertEqual(attendance.attendance_source, 'fingerprint')
        self.assertTrue(attendance.check_out)

    def test_duplicate_log_prevention(self):
        Log = self.env['fingerprint.device.log']
        Log.create({
            'device_id': self.device.id,
            'external_id': 'EXT001',
            'device_user_id': 'FP001',
            'event_time': datetime(2026, 6, 1, 8, 0, 0),
            'punch_type': 'check_in',
            'state': 'processed',
            'employee_id': self.employee.id,
        })
        from odoo.addons.hr_attendance_custom_ext.services.hikvision_connector import HikvisionConnector
        connector = HikvisionConnector(self.device)
        created, stats = connector.sync_device_logs()
        self.assertFalse(created.filtered(lambda log: log.external_id == 'EXT001'))
        self.assertEqual(
            Log.search_count([
                ('device_id', '=', self.device.id),
                ('external_id', '=', 'EXT001'),
            ]),
            1,
        )

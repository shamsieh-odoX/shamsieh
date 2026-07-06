# -*- coding: utf-8 -*-

import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import HttpCase, TransactionCase

from odoo.addons.hr_attendance_custom_ext.services.hikvision_connector import HikvisionConnector
from odoo.addons.hr_attendance_custom_ext.services.hikvision_push_parser import (
    parse_hikvision_push_body,
)

SAMPLE_EVENT = {
    'serialNo': 9001,
    'employeeNoString': '2',
    'name': 'Anton',
    'time': '2026-07-05T13:11:17',
    'major': 5,
    'minor': 38,
    'currentVerifyMode': 'fp',
}


class TestHikvisionPushParser(TransactionCase):

    def test_parse_json_wrapped_body(self):
        body = json.dumps({'AccessControllerEvent': SAMPLE_EVENT}).encode()
        parsed = parse_hikvision_push_body(body, 'application/json')
        self.assertEqual(parsed['serialNo'], 9001)

    def test_parse_flat_json_body(self):
        body = json.dumps(SAMPLE_EVENT).encode()
        parsed = parse_hikvision_push_body(body, 'application/json')
        self.assertEqual(parsed['employeeNoString'], '2')

    def test_parse_multipart_body(self):
        json_part = json.dumps(SAMPLE_EVENT)
        body = (
            b'--boundary\r\n'
            b'Content-Disposition: form-data; name="AccessControllerEvent"\r\n'
            b'Content-Type: application/json\r\n\r\n'
            + json_part.encode()
            + b'\r\n--boundary--\r\n'
        )
        parsed = parse_hikvision_push_body(
            body, 'multipart/form-data; boundary=boundary',
        )
        self.assertEqual(parsed['serialNo'], 9001)

    def test_parse_empty_body_raises(self):
        with self.assertRaises(ValueError):
            parse_hikvision_push_body(b'', 'application/json')


class TestHikvisionPushIngest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param(
            'web.base.url', 'http://localhost:8069',
        )
        cls.employee = cls.env['hr.employee'].create({
            'name': 'HTTP Listen Employee',
            'biometric_device_user_id': 'HL001',
        })
        cls.device = cls.env['fingerprint.device'].create({
            'name': 'HTTP Listen Device',
            'api_type': 'hikvision',
            'device_ip': '127.0.0.1',
            'username': 'admin',
            'password': 'test',
            'http_listening_enabled': True,
            'http_listening_allowed_ips': '127.0.0.1',
        })
        cls.token = cls.device.http_listening_token

    def test_enable_generates_token_and_url(self):
        self.assertTrue(self.token)
        self.assertIn(self.token, self.device.http_listening_url)
        self.assertIn('/hikvision/event/', self.device.http_listening_url)

    def test_ingest_push_event_stores_odoo_employee_name(self):
        connector = HikvisionConnector(self.device)
        payload = dict(SAMPLE_EVENT)
        payload['employeeNoString'] = 'HL001'
        payload['name'] = 'Scanner Label'
        payload['serialNo'] = 9104
        result = connector.ingest_push_event(payload)
        self.assertEqual(result['action'], 'stored')
        log = result['log']
        self.assertEqual(log.employee_name, self.employee.name)
        self.assertEqual(log.display_employee_name, self.employee.name)

    def test_ingest_push_event_stores_and_processes(self):
        connector = HikvisionConnector(self.device)
        payload = dict(SAMPLE_EVENT)
        payload['employeeNoString'] = 'HL001'
        payload['serialNo'] = 9100
        result = connector.ingest_push_event(payload)
        self.assertEqual(result['action'], 'stored')
        log = result['log']
        self.assertEqual(log.state, 'processed')
        self.assertTrue(log.attendance_id)

    def test_cron_skips_poll_when_http_listening_is_live(self):
        self.device.write({
            'http_listening_last_at': fields.Datetime.now(),
            'sync_interval_minutes': 15.0,
        })
        with patch.object(type(self.device), '_sync_device') as mock_sync:
            self.env['fingerprint.device']._cron_sync_all()
            mock_sync.assert_not_called()

    def test_cron_polls_when_http_listening_is_stale(self):
        self.device.write({
            'http_listening_last_at': fields.Datetime.now() - timedelta(minutes=20),
            'sync_interval_minutes': 15.0,
            'last_sync_at': False,
        })
        with patch.object(type(self.device), '_sync_device') as mock_sync:
            self.env['fingerprint.device']._cron_sync_all()
            mock_sync.assert_called_once()

    def test_ingest_duplicate(self):
        connector = HikvisionConnector(self.device)
        payload = dict(SAMPLE_EVENT)
        payload['employeeNoString'] = 'HL001'
        payload['serialNo'] = 9101
        connector.ingest_push_event(payload)
        result = connector.ingest_push_event(payload)
        self.assertEqual(result['action'], 'duplicate')

    def test_door_event_skipped_by_default(self):
        connector = HikvisionConnector(self.device)
        payload = {
            'serialNo': 9102,
            'employeeNoString': '',
            'time': '2026-07-05T13:11:17',
            'major': 5,
            'minor': 21,
        }
        result = connector.ingest_push_event(payload)
        self.assertEqual(result['action'], 'skipped')

    def test_door_event_ignored_when_storing_ignored(self):
        self.device.write({'store_ignored_events': True})
        connector = HikvisionConnector(self.device)
        payload = {
            'serialNo': 9103,
            'employeeNoString': '',
            'time': '2026-07-05T13:11:17',
            'major': 5,
            'minor': 21,
        }
        result = connector.ingest_push_event(payload)
        self.assertEqual(result['action'], 'ignored')


class TestHikvisionHttpListeningController(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))
        cls.env['ir.config_parameter'].sudo().set_param('web.base.url', cls.base_url())
        cls.employee = cls.env['hr.employee'].create({
            'name': 'HTTP Controller Employee',
            'biometric_device_user_id': 'HC001',
        })
        cls.device = cls.env['fingerprint.device'].create({
            'name': 'HTTP Controller Device',
            'api_type': 'hikvision',
            'device_ip': '127.0.0.1',
            'username': 'admin',
            'password': 'test',
            'http_listening_enabled': True,
            'http_listening_allowed_ips': '127.0.0.1',
        })
        cls.token = cls.device.http_listening_token

    def _post_event(self, token, payload, status=200):
        response = self.url_open(
            f'/hikvision/event/{token}',
            json={'AccessControllerEvent': payload},
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, status)
        return response.json()

    def test_valid_push(self):
        payload = dict(SAMPLE_EVENT)
        payload['employeeNoString'] = 'HC001'
        payload['serialNo'] = 9200
        body = self._post_event(self.token, payload)
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['action'], 'stored')
        log = self.env['fingerprint.device.log'].search([
            ('device_id', '=', self.device.id),
            ('external_id', '=', '9200'),
        ], limit=1)
        self.assertTrue(log)
        self.assertEqual(log.state, 'processed')

    def test_wrong_token(self):
        response = self.url_open(
            '/hikvision/event/invalid-token-xyz',
            json=SAMPLE_EVENT,
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, 404)

    def test_disabled_device(self):
        self.device.write({'http_listening_enabled': False})
        response = self.url_open(
            f'/hikvision/event/{self.token}',
            json=SAMPLE_EVENT,
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, 404)

    def test_wrong_ip(self):
        self.device.write({'http_listening_allowed_ips': '192.168.100.85'})
        response = self.url_open(
            f'/hikvision/event/{self.token}',
            json={'AccessControllerEvent': SAMPLE_EVENT},
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, 403)

    def test_duplicate_push(self):
        payload = dict(SAMPLE_EVENT)
        payload['employeeNoString'] = 'HC001'
        payload['serialNo'] = 9201
        self._post_event(self.token, payload)
        body = self._post_event(self.token, payload)
        self.assertEqual(body['action'], 'duplicate')

    def test_bearer_token_auth(self):
        payload = dict(SAMPLE_EVENT)
        payload['employeeNoString'] = 'HC001'
        payload['serialNo'] = 9202
        response = self.url_open(
            '/hikvision/event/unused-path-token',
            json={'AccessControllerEvent': payload},
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.token}',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['action'], 'stored')

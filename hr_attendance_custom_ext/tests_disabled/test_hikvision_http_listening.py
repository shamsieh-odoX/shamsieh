# -*- coding: utf-8 -*-

import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import HttpCase, TransactionCase

from odoo.addons.hr_attendance_custom_ext.services.hikvision_connector import HikvisionConnector
from odoo.addons.hr_attendance_custom_ext.services.hikvision_push_parser import (
    extract_hikvision_push_from_request,
    parse_hikvision_push_body,
    parse_hikvision_push_form,
    parse_hikvision_push_route_kwargs,
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

SAMPLE_EVENT_LOG = {
    'eventType': 'AccessControllerEvent',
    'majorEventType': 5,
    'subEventType': 38,
    'serialNo': 9001,
    'verifyNo': 42,
    'dateTime': '2026-07-05T13:11:17',
    'employeeNoString': '2',
    'name': 'Anton',
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

    def test_parse_werkzeug_form_event_log(self):
        parsed = parse_hikvision_push_form({
            'event_log': json.dumps(SAMPLE_EVENT_LOG),
        })
        self.assertEqual(parsed['employeeNoString'], '2')

    def test_parse_werkzeug_form_access_controller_event(self):
        parsed = parse_hikvision_push_form({
            'AccessControllerEvent': json.dumps(SAMPLE_EVENT),
        })
        self.assertEqual(parsed['serialNo'], 9001)

    def test_parse_route_kwargs_dict(self):
        parsed = parse_hikvision_push_route_kwargs({
            'event_log': SAMPLE_EVENT_LOG,
        })
        self.assertEqual(parsed['serialNo'], 9001)

    def test_extract_from_parsed_form_when_body_empty(self):
        class _FormRequest:
            content_type = 'multipart/form-data; boundary=MIME_boundary'
            form = {'event_log': json.dumps(SAMPLE_EVENT_LOG)}
            files = {}

            def get_data(self, cache=True, as_text=False):
                return b''

            @property
            def content_length(self):
                return 0

            @property
            def environ(self):
                return {}

        parsed = extract_hikvision_push_from_request(_FormRequest())
        self.assertEqual(parsed['employeeNoString'], '2')


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
            'auto_sync': True,
        })
        with patch.object(type(self.device), '_sync_device') as mock_sync:
            self.env['fingerprint.device']._cron_sync_all()
            mock_sync.assert_called_once()

    def test_cron_skips_poll_when_auto_sync_disabled(self):
        self.device.write({
            'auto_sync': False,
            'http_listening_last_at': fields.Datetime.now() - timedelta(minutes=20),
            'last_sync_at': False,
        })
        with patch.object(type(self.device), '_sync_device') as mock_sync:
            self.env['fingerprint.device']._cron_sync_all()
            mock_sync.assert_not_called()

    def test_touch_http_listening_last_at_throttled(self):
        self.device.write({'http_listening_last_at': fields.Datetime.now()})
        before = self.device.http_listening_last_at
        self.device._touch_http_listening_last_at(throttle_seconds=60)
        self.assertEqual(self.device.http_listening_last_at, before)

    def test_touch_http_listening_last_at_forced(self):
        past = fields.Datetime.now() - timedelta(minutes=5)
        self.device.write({'http_listening_last_at': past})
        self.device._touch_http_listening_last_at(force=True)
        self.assertGreater(self.device.http_listening_last_at, past)

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
            'barcode': 'HC001',
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

    def _post_event_log(self, token, payload, status=200):
        event_log = json.dumps(payload)
        body = (
            b'--boundary\r\n'
            b'Content-Disposition: form-data; name="event_log"\r\n\r\n'
            + event_log.encode()
            + b'\r\n--boundary--\r\n'
        )
        response = self.url_open(
            f'/hikvision/event/{token}',
            data=body,
            headers={'Content-Type': 'multipart/form-data; boundary=boundary'},
        )
        self.assertEqual(response.status_code, status)
        return response.json()

    def test_valid_push_records_payload(self):
        payload = dict(SAMPLE_EVENT_LOG)
        payload['serialNo'] = 9200
        payload['employeeNoString'] = 'HC001'
        payload['attendanceStatus'] = 'checkIn'
        body = self._post_event_log(self.token, payload)
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body.get('punch_type'), 'check_in')
        attendance = self.env['hr.attendance'].search([
            ('employee_id', '=', self.employee.id),
        ], limit=1)
        self.assertTrue(attendance)
        self.assertEqual(attendance.attendance_source, 'fingerprint')
        self.assertTrue(self.device.http_listening_last_at)

    def test_unknown_payload_keys_still_recorded(self):
        payload = dict(SAMPLE_EVENT_LOG)
        payload['serialNo'] = 9203
        payload['employeeNoString'] = 'HC001'
        payload['attendanceStatus'] = 'checkIn'
        payload['customField'] = 'probe'
        body = self._post_event_log(self.token, payload)
        self.assertEqual(body['status'], 'ok')
        attendance = self.env['hr.attendance'].search([
            ('employee_id', '=', self.employee.id),
        ], limit=1)
        self.assertTrue(attendance)

    def test_wrong_token(self):
        event_log = json.dumps(SAMPLE_EVENT_LOG)
        body = (
            b'--boundary\r\n'
            b'Content-Disposition: form-data; name="event_log"\r\n\r\n'
            + event_log.encode()
            + b'\r\n--boundary--\r\n'
        )
        response = self.url_open(
            '/hikvision/event/invalid-token-xyz',
            data=body,
            headers={'Content-Type': 'multipart/form-data; boundary=boundary'},
        )
        self.assertEqual(response.status_code, 404)

    def test_disabled_device(self):
        self.device.write({'http_listening_enabled': False})
        event_log = json.dumps(SAMPLE_EVENT_LOG)
        body = (
            b'--boundary\r\n'
            b'Content-Disposition: form-data; name="event_log"\r\n\r\n'
            + event_log.encode()
            + b'\r\n--boundary--\r\n'
        )
        response = self.url_open(
            f'/hikvision/event/{self.token}',
            data=body,
            headers={'Content-Type': 'multipart/form-data; boundary=boundary'},
        )
        self.assertEqual(response.status_code, 404)

    def test_wrong_ip(self):
        self.device.write({'http_listening_allowed_ips': '192.168.100.85'})
        payload = dict(SAMPLE_EVENT_LOG)
        response = self.url_open(
            f'/hikvision/event/{self.token}',
            data=(
                b'--boundary\r\n'
                b'Content-Disposition: form-data; name="event_log"\r\n\r\n'
                + json.dumps(payload).encode()
                + b'\r\n--boundary--\r\n'
            ),
            headers={'Content-Type': 'multipart/form-data; boundary=boundary'},
        )
        self.assertEqual(response.status_code, 403)

    def test_duplicate_push_returns_ok(self):
        payload = dict(SAMPLE_EVENT_LOG)
        payload['serialNo'] = 9201
        self._post_event_log(self.token, payload)
        body = self._post_event_log(self.token, payload)
        self.assertEqual(body, {'status': 'ok'})
        logs = self.env['fingerprint.device.log'].search([
            ('device_id', '=', self.device.id),
            ('serial_no', '=', '9201'),
        ])
        self.assertEqual(len(logs), 1)

    def test_bearer_token_auth(self):
        payload = dict(SAMPLE_EVENT_LOG)
        payload['serialNo'] = 9202
        event_log = json.dumps(payload)
        body = (
            b'--boundary\r\n'
            b'Content-Disposition: form-data; name="event_log"\r\n\r\n'
            + event_log.encode()
            + b'\r\n--boundary--\r\n'
        )
        response = self.url_open(
            '/hikvision/event/unused-path-token',
            data=body,
            headers={
                'Content-Type': 'multipart/form-data; boundary=boundary',
                'Authorization': f'Bearer {self.token}',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_missing_event_log_still_returns_ok(self):
        body = b'--boundary\r\n--boundary--\r\n'
        response = self.url_open(
            f'/hikvision/event/{self.token}',
            data=body,
            headers={'Content-Type': 'multipart/form-data; boundary=boundary'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

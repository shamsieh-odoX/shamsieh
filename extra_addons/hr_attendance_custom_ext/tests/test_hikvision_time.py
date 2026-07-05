# -*- coding: utf-8 -*-

from datetime import datetime, timezone
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from odoo.addons.hr_attendance_custom_ext.services.hikvision import (
    HikvisionClient,
    _acs_pagination_has_more,
    _iso_for_device,
)


class TestHikvisionTime(TransactionCase):

    def test_iso_for_device_uses_named_timezone(self):
        dt = datetime(2026, 7, 5, 10, 28, 58, tzinfo=timezone.utc)
        self.assertEqual(
            _iso_for_device(dt, 'Asia/Amman'),
            '2026-07-05T13:28:58',
        )

    def test_event_dedupe_key_prefers_serial(self):
        key = HikvisionClient._event_dedupe_key({
            'serialNo': 4846,
            'employeeNoString': '6',
            'time': '2026-07-05T13:11:17',
        })
        self.assertEqual(key, 'serial:4846')

    def test_get_access_events_returns_empty_when_variants_succeed_with_no_events(self):
        client = HikvisionClient('127.0.0.1', 80, 'user', 'pass')
        start = datetime(2026, 7, 5, 10, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 7, 5, 11, 0, 0, tzinfo=timezone.utc)
        with patch.object(client, '_fetch_acs_events_once', return_value=[]):
            events = client.get_access_events(start, end, device_tz='Asia/Riyadh')
        self.assertEqual(events, [])

    def test_acs_event_cond_variants_require_major_minor(self):
        client = HikvisionClient('127.0.0.1', 80, 'user', 'pass')
        start = datetime(2026, 7, 5, 10, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 7, 5, 11, 0, 0, tzinfo=timezone.utc)
        variants = client._acs_event_cond_variants(start, end, 'Asia/Riyadh')
        self.assertEqual(len(variants), 2)
        for variant in variants:
            self.assertIn('major', variant)
            self.assertIn('minor', variant)

    def test_acs_pagination_has_more_on_full_page_without_more_status(self):
        block = {'responseStatusStrg': 'OK', 'numOfMatches': 30}
        self.assertTrue(_acs_pagination_has_more(block, 0, 30, 30))

    def test_acs_pagination_stops_when_partial_page(self):
        block = {'responseStatusStrg': 'OK', 'numOfMatches': 12}
        self.assertFalse(_acs_pagination_has_more(block, 30, 12, 30))

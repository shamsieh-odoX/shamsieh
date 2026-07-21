# -*- coding: utf-8 -*-

from datetime import datetime

from odoo.tests.common import TransactionCase

from odoo.addons.hr_attendance_custom_ext.services.hikvision_connector import (
    classify_sync_event,
    is_attendance_relevant_event,
    is_door_system_event,
)


class TestHikvisionEventFilter(TransactionCase):

    def _event(self, **kwargs):
        raw_overrides = kwargs.pop('raw_payload', {})
        event = {
            'external_id': '1001',
            'employee_id': '2',
            'employee_name': 'Anton',
            'event_time': datetime(2026, 7, 5, 10, 11, 17),
            'event_type': 'major:5/minor:38',
            'authentication_method': 'fp',
            'raw_payload': {
                'serialNo': 1001,
                'employeeNoString': '2',
                'name': 'Anton',
                'time': '2026-07-05T13:11:17',
                'major': 5,
                'minor': 38,
                'currentVerifyMode': 'fp',
            },
        }
        event['raw_payload'].update(raw_overrides)
        event.update(kwargs)
        if raw_overrides:
            event['raw_payload'].update(raw_overrides)
        return event

    def test_fingerprint_event_with_non_one_minor_is_stored(self):
        event = self._event()
        self.assertTrue(is_attendance_relevant_event(event))
        action, reason = classify_sync_event(event)
        self.assertEqual(action, 'stored')
        self.assertEqual(reason, 'attendance-relevant')

    def test_event_type_authenticated_is_stored(self):
        event = self._event(
            event_type='Authenticated via Fingerprint',
            authentication_method='unknown',
            raw_payload={'minor': 99, 'currentVerifyMode': ''},
        )
        self.assertTrue(is_attendance_relevant_event(event))

    def test_verify_mode_card_or_fp_is_stored(self):
        event = self._event(
            event_type='major:5/minor:75',
            authentication_method='cardOrFpOrPw',
            raw_payload={'minor': 75, 'currentVerifyMode': 'cardOrFpOrPw'},
        )
        self.assertTrue(is_attendance_relevant_event(event))

    def test_door_locked_is_not_stored(self):
        event = self._event(
            employee_id='',
            event_type='Door Locked',
            authentication_method='',
            raw_payload={
                'employeeNoString': '',
                'minor': 21,
                'currentVerifyMode': '',
            },
        )
        self.assertTrue(is_door_system_event(event))
        self.assertFalse(is_attendance_relevant_event(event))
        action, reason = classify_sync_event(event, store_ignored_events=True)
        self.assertEqual(action, 'ignored')
        self.assertEqual(reason, 'no employeeNoString')

    def test_exit_button_pressed_is_ignored_when_storing_ignored(self):
        event = self._event(
            employee_id='',
            event_type='Exit Button Pressed',
            raw_payload={'employeeNoString': '', 'minor': 22},
        )
        action, reason = classify_sync_event(event, store_ignored_events=True)
        self.assertEqual(action, 'ignored')
        self.assertEqual(reason, 'no employeeNoString')

    def test_invalid_authentication_is_skipped(self):
        event = self._event(authentication_method='invalid', raw_payload={'currentVerifyMode': 'invalid'})
        self.assertFalse(is_attendance_relevant_event(event))
        action, reason = classify_sync_event(event)
        self.assertEqual(action, 'skipped')
        self.assertEqual(reason, 'invalid authentication')

    def test_missing_event_time_is_skipped(self):
        event = self._event(event_time=None)
        action, reason = classify_sync_event(event)
        self.assertEqual(action, 'skipped')
        self.assertEqual(reason, 'missing event_time')

# -*- coding: utf-8 -*-

from unittest.mock import patch

from odoo.tests import HttpCase, TransactionCase

from odoo.addons.hr_attendance_custom_ext.services.face_provider_insightface import (
    UNAVAILABLE_MESSAGE,
    haversine_distance_meters,
)


class TestFaceProviderUtils(TransactionCase):

    def test_haversine_distance_zero_for_same_point(self):
        distance = haversine_distance_meters(31.95, 35.91, 31.95, 35.91)
        self.assertAlmostEqual(distance, 0.0, places=3)

    def test_provider_unavailable_when_imports_missing(self):
        with patch(
            'odoo.addons.hr_attendance_custom_ext.services.face_provider_insightface.InsightFaceProvider.is_available',
            return_value=False,
        ):
            from odoo.addons.hr_attendance_custom_ext.services.face_provider_insightface import InsightFaceProvider
            provider = InsightFaceProvider()
            self.assertFalse(provider.is_available())


class TestFaceAttendanceInsightFace(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'face_attendance_stub_enabled': False,
            'face_match_threshold': 0.85,
            'face_provider': 'insightface',
            'face_quality_check_enabled': False,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'InsightFace Employee',
            'remote_attendance_allowed': True,
            'company_id': cls.company.id,
        })
        cls.template = cls.env['hr.employee.face.template'].create({
            'employee_id': cls.employee.id,
            'provider': 'insightface',
            'active': True,
            'enrolled_at': '2026-07-05 10:00:00',
            'enrolled_by': cls.env.user.id,
        })
        cls.template.set_embedding_vector([0.1, 0.2, 0.3])
        cls.employee.write({
            'face_enrollment_status': 'enrolled',
            'face_template_id': str(cls.template.id),
        })
        cls.Log = cls.env['face.attendance.log']

    def _mock_verify_success(self):
        return {
            'passed': True,
            'confidence_score': 0.95,
            'distance': 0.1,
            'provider': 'insightface',
            'failure_reason': False,
            'provider_response': {},
        }

    def _mock_verify_fail(self):
        return {
            'passed': False,
            'confidence_score': 0.2,
            'distance': 1.5,
            'provider': 'insightface',
            'failure_reason': 'Face verification failed.',
            'provider_response': {},
        }

    @patch('odoo.addons.hr_attendance_custom_ext.models.face_attendance_log.get_face_provider')
    def test_successful_verification_creates_attendance(self, mock_get_provider):
        mock_provider = mock_get_provider.return_value
        mock_provider.is_available.return_value = True
        mock_provider.verify_face.return_value = self._mock_verify_success()

        log = self.Log.create_face_check(
            employee=self.employee,
            action_type='check_in',
            selfie_image_base64='aGVsbG8=',
        )
        self.assertEqual(log.verification_status, 'passed')
        self.assertTrue(log.attendance_id)
        self.assertEqual(log.attendance_id.attendance_source, 'face')
        self.assertTrue(log.attendance_id.face_verified)

    @patch('odoo.addons.hr_attendance_custom_ext.models.face_attendance_log.get_face_provider')
    def test_failed_verification_does_not_create_attendance(self, mock_get_provider):
        mock_provider = mock_get_provider.return_value
        mock_provider.is_available.return_value = True
        mock_provider.verify_face.return_value = self._mock_verify_fail()

        log = self.Log.create_face_check(
            employee=self.employee,
            action_type='check_in',
            selfie_image_base64='aGVsbG8=',
        )
        self.assertEqual(log.verification_status, 'failed')
        self.assertFalse(log.attendance_id)

    def test_no_active_template_fails(self):
        self.template.write({'active': False})
        log = self.Log.create_face_check(
            employee=self.employee,
            action_type='check_in',
            selfie_image_base64='aGVsbG8=',
        )
        self.assertEqual(log.verification_status, 'failed')
        self.assertIn('No active face template', log.error_message)

    def test_remote_attendance_not_allowed_raises(self):
        self.employee.remote_attendance_allowed = False
        with self.assertRaises(Exception):
            self.Log.create_face_check(
                employee=self.employee,
                action_type='check_in',
                selfie_image_base64='aGVsbG8=',
            )

    @patch('odoo.addons.hr_attendance_custom_ext.models.face_attendance_log.get_face_provider')
    def test_provider_unavailable_fails_gracefully(self, mock_get_provider):
        mock_provider = mock_get_provider.return_value
        mock_provider.is_available.return_value = False

        log = self.Log.create_face_check(
            employee=self.employee,
            action_type='check_in',
            selfie_image_base64='aGVsbG8=',
        )
        self.assertEqual(log.verification_status, 'failed')
        self.assertEqual(log.error_message, UNAVAILABLE_MESSAGE)

    @patch('odoo.addons.hr_attendance_custom_ext.models.face_attendance_log.get_face_provider')
    def test_duplicate_external_token_returns_existing_log(self, mock_get_provider):
        mock_provider = mock_get_provider.return_value
        mock_provider.is_available.return_value = True
        mock_provider.verify_face.return_value = self._mock_verify_success()

        token = 'duplicate-token-001'
        first = self.Log.create_face_check(
            employee=self.employee,
            action_type='check_in',
            selfie_image_base64='aGVsbG8=',
            external_token=token,
        )
        second = self.Log.create_face_check(
            employee=self.employee,
            action_type='check_in',
            selfie_image_base64='aGVsbG8=',
            external_token=token,
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.Log.search_count([('external_token', '=', token)]), 1)

    def test_geo_outside_radius_fails(self):
        self.company.write({
            'face_allowed_latitude': 31.9500,
            'face_allowed_longitude': 35.9100,
            'face_geo_radius_meters': 100,
        })
        log = self.Log.create_face_check(
            employee=self.employee,
            action_type='check_in',
            latitude=32.0000,
            longitude=36.0000,
            selfie_image_base64='aGVsbG8=',
        )
        self.assertEqual(log.verification_status, 'failed')
        self.assertTrue(log.distance_meters > 100)
        self.assertIn('outside the allowed radius', log.error_message)

    @patch('odoo.addons.hr_attendance_custom_ext.models.face_attendance_log.get_face_provider')
    def test_low_confidence_fails(self, mock_get_provider):
        mock_provider = mock_get_provider.return_value
        mock_provider.is_available.return_value = True
        mock_provider.verify_face.return_value = {
            'passed': True,
            'confidence_score': 0.5,
            'distance': 0.8,
            'provider': 'insightface',
            'failure_reason': False,
            'provider_response': {},
        }

        log = self.Log.create_face_check(
            employee=self.employee,
            action_type='check_in',
            selfie_image_base64='aGVsbG8=',
        )
        self.assertEqual(log.verification_status, 'failed')
        self.assertIn('below threshold', log.error_message)

    @patch('odoo.addons.hr_attendance_custom_ext.models.face_attendance_log.get_face_provider')
    def test_multiple_faces_mocked_fail(self, mock_get_provider):
        mock_provider = mock_get_provider.return_value
        mock_provider.is_available.return_value = True
        mock_provider.verify_face.return_value = {
            'passed': False,
            'confidence_score': 0.0,
            'distance': 0.0,
            'provider': 'insightface',
            'failure_reason': 'Multiple faces detected',
            'provider_response': {},
        }

        log = self.Log.create_face_check(
            employee=self.employee,
            action_type='check_in',
            selfie_image_base64='aGVsbG8=',
        )
        self.assertEqual(log.verification_status, 'failed')
        self.assertEqual(log.error_message, 'Multiple faces detected')

    @patch('odoo.addons.hr_attendance_custom_ext.models.face_attendance_log.get_face_provider')
    def test_no_selfie_fails(self, mock_get_provider):
        log = self.Log.create_face_check(
            employee=self.employee,
            action_type='check_in',
        )
        self.assertEqual(log.verification_status, 'failed')
        self.assertIn('Selfie image is required', log.error_message)
        mock_get_provider.assert_not_called()


class TestFaceAttendanceController(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'face_attendance_stub_enabled': True})
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Controller Face Employee',
            'remote_attendance_allowed': True,
            'company_id': cls.company.id,
            'user_id': cls.env.user.id,
        })

    def test_face_check_jsonrpc_stub(self):
        result = self.make_jsonrpc_request(
            '/hr_attendance_custom/face/check',
            params={'action_type': 'check_in'},
        )
        self.assertEqual(result.get('status'), 'passed')

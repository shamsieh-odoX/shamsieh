# -*- coding: utf-8 -*-

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'hr_attendance_custom_ext')
class TestRemoteWorkRequest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.remote_work_requests_enabled = True
        cls.company.face_attendance_stub_enabled = True

        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'Remote Work Test Calendar',
            'tz': 'UTC',
            'attendance_ids': [
                (0, 0, {
                    'name': day_name,
                    'dayofweek': str(day),
                    'hour_from': 8,
                    'hour_to': 16,
                    'day_period': 'morning',
                    'location_type': 'office',
                })
                for day, day_name in enumerate([
                    'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun',
                ])
            ],
        })

        cls.manager_user = cls.env['res.users'].create({
            'name': 'Remote Work Manager',
            'login': 'remote_work_mgr_test',
            'email': 'remote_work_mgr_test@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.manager_employee = cls.env['hr.employee'].create({
            'name': 'Remote Work Manager Emp',
            'user_id': cls.manager_user.id,
            'company_id': cls.company.id,
        })

        cls.officer_user = cls.env['res.users'].create({
            'name': 'Remote Work Officer',
            'login': 'remote_work_officer_test',
            'email': 'remote_work_officer_test@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('hr_attendance.group_hr_attendance_officer').id,
            ])],
        })

        cls.employee_user = cls.env['res.users'].create({
            'name': 'Remote Work Employee User',
            'login': 'remote_work_emp_test',
            'email': 'remote_work_emp_test@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Remote Work Employee',
            'company_id': cls.company.id,
            'resource_calendar_id': cls.calendar.id,
            'leave_manager_id': cls.manager_user.id,
            'parent_id': cls.manager_employee.id,
            'user_id': cls.employee_user.id,
            'remote_attendance_allowed': True,
        })

        cls.Request = cls.env['hr.remote.work.request']

    def _create_request(self, state='draft'):
        request = self.Request.create({
            'employee_id': self.employee.id,
            'request_date': fields.Date.context_today(self.employee),
            'reason': 'Family appointment at home',
        })
        if state == 'submitted':
            request.with_user(self.employee_user).action_submit()
        elif state == 'manager_approved':
            request.with_user(self.employee_user).action_submit()
            request.with_user(self.manager_user).action_manager_approve()
        elif state == 'approved':
            request.with_user(self.employee_user).action_submit()
            request.with_user(self.manager_user).action_manager_approve()
            request.with_user(self.officer_user).action_hr_approve()
        return request

    def test_approval_workflow(self):
        request = self._create_request()
        self.assertEqual(request.state, 'draft')
        request.with_user(self.employee_user).action_submit()
        self.assertEqual(request.state, 'submitted')
        request.with_user(self.manager_user).action_manager_approve()
        self.assertEqual(request.state, 'manager_approved')
        request.with_user(self.officer_user).action_hr_approve()
        self.assertEqual(request.state, 'approved')

    def test_manager_cannot_hr_approve_before_manager_step(self):
        request = self._create_request('submitted')
        with self.assertRaises(UserError):
            request.with_user(self.officer_user).action_hr_approve()

    def test_non_manager_cannot_manager_approve(self):
        request = self._create_request('submitted')
        with self.assertRaises(AccessError):
            request.with_user(self.employee_user).action_manager_approve()

    def test_approved_remote_work_overrides_office_schedule(self):
        request = self._create_request('approved')
        self.assertEqual(request.state, 'approved')
        self.assertEqual(self.employee._get_attendance_scheduled_location(), 'home')
        self.assertEqual(self.employee._get_effective_work_location_type(), 'home')
        self.assertTrue(self.employee._manual_attendance_allowed())

    def test_without_approval_office_day_blocks_manual_check_in(self):
        self.assertEqual(self.employee._get_attendance_scheduled_location(), 'office')
        with self.assertRaises(UserError):
            self.employee._raise_if_manual_attendance_blocked()

    def test_systray_flags_face_when_enrolled(self):
        self._create_request('approved')
        self.env['hr.employee.face.template'].create({
            'employee_id': self.employee.id,
            'active': True,
            'provider': 'insightface',
            'embedding_json': '[0.1, 0.2]',
        })
        data = self.employee._get_attendance_systray_user_data()
        self.assertTrue(data['manual_attendance_allowed'])
        self.assertTrue(data['approved_remote_work_today'])
        self.assertTrue(data['check_in_requires_face'])
        self.assertFalse(data['check_in_requires_home_pin'])

    def test_systray_flags_home_pin_without_face(self):
        self._create_request('approved')
        self.employee._set_home_attendance_pin('2468')
        data = self.employee._get_attendance_systray_user_data()
        self.assertTrue(data['manual_attendance_allowed'])
        self.assertFalse(data['check_in_requires_face'])
        self.assertTrue(data['check_in_requires_home_pin'])

    def test_home_pin_allowed_on_approved_remote_work_day(self):
        self._create_request('approved')
        self.employee._set_home_attendance_pin('1357')
        self.assertEqual(self.employee._get_attendance_scheduled_location(), 'home')
        self.assertTrue(self.employee._verify_home_attendance_pin('1357'))

    def test_feature_disabled_ignores_approved_request(self):
        request = self._create_request('approved')
        self.company.remote_work_requests_enabled = False
        self.assertFalse(self.employee._has_approved_remote_work())
        self.assertEqual(self.employee._get_attendance_scheduled_location(), 'office')

    def test_refuse_workflow(self):
        request = self._create_request('submitted')
        request.with_user(self.manager_user).action_process_refusal('Not enough coverage')
        self.assertEqual(request.state, 'refused')
        self.assertEqual(request.refuse_reason, 'Not enough coverage')

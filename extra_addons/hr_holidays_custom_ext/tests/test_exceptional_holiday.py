# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'hr_holidays_custom_ext')
class TestExceptionalHoliday(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.HolidayRequest = cls.env['hr.exceptional.holiday']

        cls.hr_manager_user = cls.env['res.users'].create({
            'name': 'Holidays HR Manager',
            'login': 'eh_hr_mgr',
            'email': 'eh_hr_mgr@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('hr_holidays.group_hr_holidays_manager').id,
                cls.env.ref('hr_holidays.group_hr_holidays_user').id,
            ])],
        })
        cls.upper_manager_user = cls.env['res.users'].create({
            'name': 'Upper Manager',
            'login': 'eh_upper_mgr',
            'email': 'eh_upper_mgr@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.dept_manager_user = cls.env['res.users'].create({
            'name': 'Department Manager',
            'login': 'eh_dept_mgr',
            'email': 'eh_dept_mgr@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.requester_user = cls.env['res.users'].create({
            'name': 'Holiday Requester',
            'login': 'eh_requester',
            'email': 'eh_requester@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('hr_holidays.group_hr_holidays_user').id,
                cls.env.ref('base.group_user').id,
            ])],
        })

        cls.upper_manager = cls.env['hr.employee'].create({
            'name': 'Upper Manager Emp',
            'user_id': cls.upper_manager_user.id,
        })
        cls.dept_manager = cls.env['hr.employee'].create({
            'name': 'Department Manager Emp',
            'user_id': cls.dept_manager_user.id,
            'parent_id': cls.upper_manager.id,
        })
        cls.requester = cls.env['hr.employee'].create({
            'name': 'Holiday Requester Emp',
            'user_id': cls.requester_user.id,
            'parent_id': cls.dept_manager.id,
        })

    def _dt(self, year, month, day, hour=0, minute=0):
        return datetime(year, month, day, hour, minute, 0)

    def _create_request(self):
        return self.HolidayRequest.create({
            'name': 'Company Closure',
            'employee_id': self.requester.id,
            'company_id': self.env.company.id,
            'date_from': self._dt(2026, 8, 10, 0, 0),
            'date_to': self._dt(2026, 8, 10, 23, 59),
            'reason': 'Exceptional closure day',
        })

    def _approve_chain(self, request):
        request.with_user(self.dept_manager_user).action_approve()
        request.with_user(self.upper_manager_user).action_approve()
        request.with_user(self.hr_manager_user).action_approve()

    def test_full_approval_creates_public_holiday(self):
        request = self._create_request()
        self.assertEqual(request.state, 'draft')
        self.assertFalse(request.calendar_leave_id)

        request.with_user(self.requester_user).action_submit()
        self.assertEqual(request.state, 'submitted')
        self.assertFalse(request.calendar_leave_id)

        self._approve_chain(request)
        self.assertEqual(request.state, 'hr_approved')
        self.assertTrue(request.calendar_leave_id)
        self.assertFalse(request.calendar_leave_id.resource_id)
        self.assertEqual(request.calendar_leave_id.exceptional_holiday_id, request)

        overtime = self.env['hr.overtime.request'].new({
            'employee_id': self.requester.id,
            'start_datetime': self._dt(2026, 8, 10, 17, 0),
            'end_datetime': self._dt(2026, 8, 10, 19, 0),
        })
        self.assertTrue(
            overtime._is_public_holiday_date(
                overtime.start_datetime.date(),
                self.requester,
                self.env.company,
            )
        )

    def test_refusal_does_not_create_public_holiday(self):
        request = self._create_request()
        request.with_user(self.requester_user).action_submit()
        line = request._get_active_approval_line()
        wizard = self.env['hr.exceptional.holiday.refuse.wizard'].create({
            'holiday_request_id': request.id,
            'approval_line_id': line.id,
            'reason': 'Not approved',
        })
        wizard.with_user(self.dept_manager_user).action_refuse()

        self.assertEqual(request.state, 'refused')
        self.assertFalse(request.calendar_leave_id)

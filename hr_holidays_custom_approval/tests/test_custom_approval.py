# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'hr_holidays_custom_approval')
class TestCustomLeaveApproval(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Leave = cls.env['hr.leave']
        cls.company = cls.env.company

        cls.hr_user = cls.env['res.users'].create({
            'name': 'HR Officer Custom',
            'login': 'hr_officer_custom_appr',
            'email': 'hr_officer_custom_appr@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('hr_holidays.group_hr_holidays_user').id,
                cls.env.ref('base.group_user').id,
            ])],
        })
        cls.gm_user = cls.env['res.users'].create({
            'name': 'GM Custom',
            'login': 'gm_custom_appr',
            'email': 'gm_custom_appr@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('hr_holidays_custom_approval.group_hr_holidays_gm').id,
                cls.env.ref('base.group_user').id,
            ])],
        })
        cls.manager_user = cls.env['res.users'].create({
            'name': 'Org Manager Custom',
            'login': 'org_mgr_custom_appr',
            'email': 'org_mgr_custom_appr@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.employee_user = cls.env['res.users'].create({
            'name': 'Employee Custom',
            'login': 'emp_custom_appr',
            'email': 'emp_custom_appr@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.stranger_user = cls.env['res.users'].create({
            'name': 'Stranger Custom',
            'login': 'stranger_custom_appr',
            'email': 'stranger_custom_appr@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

        cls.hr_employee = cls.env['hr.employee'].create({
            'name': 'HR Officer Emp',
            'user_id': cls.hr_user.id,
            'company_id': cls.company.id,
        })
        cls.gm_employee = cls.env['hr.employee'].create({
            'name': 'GM Emp',
            'user_id': cls.gm_user.id,
            'company_id': cls.company.id,
        })
        cls.manager_employee = cls.env['hr.employee'].create({
            'name': 'Org Manager Emp',
            'user_id': cls.manager_user.id,
            'company_id': cls.company.id,
        })
        cls.employee_with_manager = cls.env['hr.employee'].create({
            'name': 'Employee With Manager',
            'user_id': cls.employee_user.id,
            'parent_id': cls.manager_employee.id,
            'company_id': cls.company.id,
        })
        cls.employee_no_manager_user = cls.env['res.users'].create({
            'name': 'Employee No Mgr',
            'login': 'emp_no_mgr_custom_appr',
            'email': 'emp_no_mgr_custom_appr@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.employee_no_manager = cls.env['hr.employee'].create({
            'name': 'Employee No Manager',
            'user_id': cls.employee_no_manager_user.id,
            'company_id': cls.company.id,
        })

        cls.company.time_off_gm_id = cls.gm_employee

        cls.leave_type = cls.env['hr.leave.type'].create({
            'name': 'Custom Approval Leave',
            'requires_allocation': False,
            'leave_validation_type': 'both',
        })

    def _create_leave(self, employee):
        return self.Leave.create({
            'name': 'Custom approval test',
            'employee_id': employee.id,
            'holiday_status_id': self.leave_type.id,
            'request_date_from': date(2026, 11, 2),
            'request_date_to': date(2026, 11, 3),
        })

    def test_manager_then_hr_flow(self):
        leave = self._create_leave(self.employee_with_manager)
        self.assertEqual(leave.state, 'confirm')
        self.assertEqual(leave.approval_flow, 'manager_hr')
        self.assertIn(self.manager_user, leave.current_approver_user_ids)
        self.assertTrue(leave.with_user(self.manager_user).can_approve)
        self.assertFalse(leave.with_user(self.hr_user).can_approve)

        leave.with_user(self.manager_user).action_approve()
        self.assertEqual(leave.state, 'validate1')
        self.assertEqual(leave.first_approver_id, self.manager_employee)
        self.assertIn(self.hr_user, leave.current_approver_user_ids)
        self.assertTrue(leave.with_user(self.hr_user).can_validate)

        leave.with_user(self.hr_user).action_approve()
        self.assertEqual(leave.state, 'validate')
        self.assertEqual(leave.second_approver_id, self.hr_employee)

    def test_hr_then_gm_flow(self):
        leave = self._create_leave(self.employee_no_manager)
        self.assertEqual(leave.approval_flow, 'hr_gm')
        self.assertIn(self.hr_user, leave.current_approver_user_ids)
        self.assertTrue(leave.with_user(self.hr_user).can_approve)

        leave.with_user(self.hr_user).action_approve()
        self.assertEqual(leave.state, 'validate1')
        self.assertIn(self.gm_user, leave.current_approver_user_ids)
        self.assertTrue(leave.with_user(self.gm_user).can_validate)

        leave.with_user(self.gm_user).action_approve()
        self.assertEqual(leave.state, 'validate')
        self.assertEqual(leave.second_approver_id, self.gm_employee)

    def test_refuse_at_step1(self):
        leave = self._create_leave(self.employee_with_manager)
        leave.with_user(self.manager_user).action_refuse()
        self.assertEqual(leave.state, 'refuse')

    def test_refuse_at_step2(self):
        leave = self._create_leave(self.employee_with_manager)
        leave.with_user(self.manager_user).action_approve()
        self.assertEqual(leave.state, 'validate1')
        leave.with_user(self.hr_user).action_refuse()
        self.assertEqual(leave.state, 'refuse')

    def test_wrong_user_cannot_approve(self):
        leave = self._create_leave(self.employee_with_manager)
        self.assertFalse(leave.with_user(self.stranger_user).can_approve)
        with self.assertRaises(Exception):
            leave.with_user(self.stranger_user).action_approve()
        self.assertEqual(leave.state, 'confirm')

    def test_manager_changed_mid_flow(self):
        leave = self._create_leave(self.employee_with_manager)
        self.assertIn(self.manager_user, leave.current_approver_user_ids)

        new_manager_user = self.env['res.users'].create({
            'name': 'New Org Manager',
            'login': 'new_org_mgr_custom_appr',
            'email': 'new_org_mgr_custom_appr@test.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        new_manager = self.env['hr.employee'].create({
            'name': 'New Org Manager Emp',
            'user_id': new_manager_user.id,
            'company_id': self.company.id,
        })
        self.employee_with_manager.parent_id = new_manager
        leave.invalidate_recordset()
        leave._compute_approval_routing()
        self.assertIn(new_manager_user, leave.current_approver_user_ids)
        self.assertNotIn(self.manager_user, leave.current_approver_user_ids)
        leave.with_user(new_manager_user).action_approve()
        self.assertEqual(leave.state, 'validate1')

    def test_missing_gm_configuration(self):
        self.company.time_off_gm_id = False
        with self.assertRaises(UserError):
            self._create_leave(self.employee_no_manager)

    def test_self_approval_escalates(self):
        """If the requester is their own parent, step1 escalates away from self."""
        self.employee_with_manager.parent_id = self.employee_with_manager
        # Recompute needs a parent that is self — treat as no manager path or escalate.
        # Our code: manager_user is requester → step1 excluded → escalate to HR.
        leave = self._create_leave(self.employee_with_manager)
        self.assertNotIn(self.employee_user, leave.step1_user_ids)
        self.assertIn(self.hr_user, leave.current_approver_user_ids)

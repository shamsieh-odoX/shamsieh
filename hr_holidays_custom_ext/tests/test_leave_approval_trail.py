# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'hr_holidays_custom_ext')
class TestLeaveApprovalTrail(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Leave = cls.env['hr.leave']
        cls.Trail = cls.env['hr.leave.approval.trail']
        cls.RefuseWizard = cls.env['hr.leave.refuse.wizard']
        cls.company = cls.env.company

        cls.manager_user = cls.env['res.users'].create({
            'name': 'Leave Manager',
            'login': 'leave_mgr_test',
            'email': 'leave_mgr_test@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('base.group_user').id,
            ])],
        })
        cls.hr_user = cls.env['res.users'].create({
            'name': 'HR Officer',
            'login': 'leave_hr_test',
            'email': 'leave_hr_test@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('hr_holidays.group_hr_holidays_user').id,
                cls.env.ref('base.group_user').id,
            ])],
        })
        cls.gm_user = cls.env['res.users'].create({
            'name': 'GM / CEO',
            'login': 'leave_gm_test',
            'email': 'leave_gm_test@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('base.group_user').id,
            ])],
        })
        cls.employee_user = cls.env['res.users'].create({
            'name': 'Leave Employee',
            'login': 'leave_emp_test',
            'email': 'leave_emp_test@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('base.group_user').id,
            ])],
        })
        cls.no_mgr_user = cls.env['res.users'].create({
            'name': 'No Manager Employee',
            'login': 'leave_nomgr_test',
            'email': 'leave_nomgr_test@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

        cls.manager_employee = cls.env['hr.employee'].create({
            'name': 'Leave Manager Emp',
            'user_id': cls.manager_user.id,
            'company_id': cls.company.id,
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
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Leave Employee Emp',
            'user_id': cls.employee_user.id,
            'leave_manager_id': cls.manager_user.id,
            'parent_id': cls.manager_employee.id,
            'company_id': cls.company.id,
        })
        # Abrar-style: reports directly to GM/CEO → HR then GM (not manager→HR).
        cls.employee_under_gm = cls.env['hr.employee'].create({
            'name': 'Direct Report Of GM',
            'user_id': cls.no_mgr_user.id,
            'parent_id': cls.gm_employee.id,
            'company_id': cls.company.id,
        })

        cls.company.time_off_gm_id = cls.gm_employee

        cls.leave_type_manager = cls.env['hr.leave.type'].create({
            'name': 'Manager Validated Leave',
            'requires_allocation': False,
            'leave_validation_type': 'manager',
        })
        cls.leave_type_both = cls.env['hr.leave.type'].create({
            'name': 'Two Step Leave',
            'requires_allocation': False,
            'leave_validation_type': 'both',
        })

    def _create_leave(self, leave_type, employee=None):
        return self.Leave.create({
            'name': 'Approval Trail Test',
            'employee_id': (employee or self.employee).id,
            'holiday_status_id': leave_type.id,
            'request_date_from': date(2026, 9, 1),
            'request_date_to': date(2026, 9, 2),
        })

    def test_submitted_trail_on_create(self):
        leave = self._create_leave(self.leave_type_manager)
        self.assertEqual(leave.state, 'confirm')
        self.assertTrue(leave.approval_trail_ids.filtered(lambda line: line.stage == 'submitted'))

    def test_manager_approval_trail(self):
        leave = self._create_leave(self.leave_type_manager)
        leave.with_user(self.manager_user).action_approve()
        self.assertEqual(leave.state, 'validate')
        stages = leave.approval_trail_ids.mapped('stage')
        self.assertIn('submitted', stages)
        self.assertIn('first_approval', stages)

    def test_manager_then_hr_flow(self):
        """Employee with middle manager: manager → HR."""
        leave = self._create_leave(self.leave_type_both)
        self.assertEqual(leave.approval_flow, 'manager_hr')
        self.assertEqual(leave.first_approver_display_id, self.manager_employee)
        self.assertEqual(leave.second_approver_display_id, self.hr_employee)
        self.assertTrue(leave.with_user(self.manager_user).can_approve)
        self.assertFalse(leave.with_user(self.hr_user).can_approve)

        leave.with_user(self.manager_user).action_approve()
        self.assertEqual(leave.state, 'validate1')
        self.assertTrue(leave.approval_trail_ids.filtered(lambda line: line.stage == 'first_approval'))
        self.assertEqual(leave.second_approver_display_id, self.hr_employee)
        self.assertFalse(leave.with_user(self.manager_user).can_validate)
        self.assertTrue(leave.with_user(self.hr_user).can_validate)

        leave.with_user(self.hr_user).action_approve()
        self.assertEqual(leave.state, 'validate')
        self.assertEqual(leave.second_approver_id, self.hr_employee)
        self.assertTrue(leave.approval_trail_ids.filtered(lambda line: line.stage == 'second_approval'))

    def test_hr_then_gm_for_direct_report_of_ceo(self):
        """Like Abrar under Basem: HR first, then company GM."""
        leave = self._create_leave(self.leave_type_both, employee=self.employee_under_gm)
        self.assertEqual(leave.approval_flow, 'hr_gm')
        self.assertEqual(leave.first_approver_display_id, self.hr_employee)
        self.assertEqual(leave.second_approver_display_id, self.gm_employee)
        self.assertTrue(leave.with_user(self.hr_user).can_approve)
        self.assertFalse(leave.with_user(self.gm_user).can_approve)

        leave.with_user(self.hr_user).action_approve()
        self.assertEqual(leave.state, 'validate1')
        self.assertEqual(leave.second_approver_display_id, self.gm_employee)
        self.assertTrue(leave.with_user(self.gm_user).can_validate)

        leave.with_user(self.gm_user).action_approve()
        self.assertEqual(leave.state, 'validate')
        self.assertEqual(leave.second_approver_id, self.gm_employee)

    def test_missing_gm_raises_for_no_middle_manager(self):
        self.company.time_off_gm_id = False
        with self.assertRaises(UserError):
            self._create_leave(self.leave_type_both, employee=self.employee_under_gm)

    def test_manager_with_officer_rights_cannot_skip_second_approval(self):
        """Manager who is also Time Off Admin must still stop at first approval."""
        self.manager_user.group_ids = [(4, self.env.ref('hr_holidays.group_hr_holidays_manager').id)]
        leave = self._create_leave(self.leave_type_both)
        leave.with_user(self.manager_user).action_approve()
        self.assertEqual(leave.state, 'validate1')
        with self.assertRaises(Exception):
            leave.with_user(self.manager_user).action_approve()
        self.assertEqual(leave.state, 'validate1')

    def test_refuse_wizard_stores_reason_and_trail(self):
        leave = self._create_leave(self.leave_type_manager)
        action = leave.with_user(self.manager_user).action_refuse()
        self.assertEqual(action['res_model'], 'hr.leave.refuse.wizard')
        wizard = self.RefuseWizard.with_context(**action['context']).create({
            'reason': 'Insufficient coverage',
        })
        wizard.with_user(self.manager_user).action_refuse()
        self.assertEqual(leave.state, 'refuse')
        self.assertEqual(leave.refuse_reason, 'Insufficient coverage')
        refused_line = leave.approval_trail_ids.filtered(lambda line: line.stage == 'refused')
        self.assertTrue(refused_line)
        self.assertEqual(refused_line.comment, 'Insufficient coverage')

    def test_print_approval_report_action(self):
        leave = self._create_leave(self.leave_type_manager)
        action = leave.action_print_approval_report()
        self.assertEqual(
            action['report_name'],
            'hr_holidays_custom_ext.report_hr_leave_approval',
        )

    def test_employee_cannot_approve_own_leave(self):
        leave = self._create_leave(self.leave_type_manager)
        with self.assertRaises(Exception):
            leave.with_user(self.employee_user).action_approve()
        self.assertEqual(leave.state, 'confirm')
        self.assertFalse(leave.with_user(self.employee_user).can_approve)
        self.assertFalse(leave.with_user(self.employee_user).can_validate)
        self.assertFalse(leave.with_user(self.employee_user).can_refuse)

    def test_employee_cannot_refuse_own_leave(self):
        leave = self._create_leave(self.leave_type_manager)
        with self.assertRaises(Exception):
            leave.with_user(self.employee_user).action_refuse()
        self.assertEqual(leave.state, 'confirm')

    def test_employee_with_admin_group_cannot_validate_own_leave(self):
        """Even Time Off Administrators cannot approve their own request."""
        self.employee_user.group_ids = [(4, self.env.ref('hr_holidays.group_hr_holidays_manager').id)]
        leave = self._create_leave(self.leave_type_both)
        self.assertFalse(leave.with_user(self.employee_user).can_approve)
        self.assertFalse(leave.with_user(self.employee_user).can_validate)
        self.assertFalse(leave.with_user(self.employee_user).can_refuse)
        self.assertFalse(leave.with_user(self.employee_user).can_second_approve)
        with self.assertRaises(Exception):
            leave.with_user(self.employee_user).action_approve()
        self.assertEqual(leave.state, 'confirm')

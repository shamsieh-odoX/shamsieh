# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'hr_overtime')
class TestHrOvertime(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.OvertimeRequest = cls.env['hr.overtime.request']
        cls.ApprovalService = cls.env['hr.approval.chain.service']
        cls.OvertimeType = cls.env['hr.overtime.type']

        cls.regular_type = cls.env.ref('hr_overtime_management.overtime_type_regular')
        cls.weekend_type = cls.env.ref('hr_overtime_management.overtime_type_weekend')
        cls.holiday_type = cls.env.ref('hr_overtime_management.overtime_type_holiday')

        cls.hr_officer = cls.env['res.users'].create({
            'name': 'Overtime HR Officer',
            'login': 'ot_hr_officer',
            'email': 'ot_hr_officer@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('hr_overtime_management.group_overtime_hr_officer').id,
                cls.env.ref('hr_overtime_management.group_overtime_user').id,
            ])],
        })

        cls.upper_manager_user = cls.env['res.users'].create({
            'name': 'Upper Manager',
            'login': 'ot_upper_mgr',
            'email': 'ot_upper_mgr@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.dept_manager_user = cls.env['res.users'].create({
            'name': 'Department Manager',
            'login': 'ot_dept_mgr',
            'email': 'ot_dept_mgr@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.single_dept_manager_user = cls.env['res.users'].create({
            'name': 'Solo Department Manager',
            'login': 'ot_solo_mgr',
            'email': 'ot_solo_mgr@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.employee_user = cls.env['res.users'].create({
            'name': 'Overtime Employee',
            'login': 'ot_employee',
            'email': 'ot_employee@test.com',
            'company_ids': [(4, cls.env.company.id)],
            'company_id': cls.env.company.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.solo_employee_user = cls.env['res.users'].create({
            'name': 'Solo Chain Employee',
            'login': 'ot_solo_emp',
            'email': 'ot_solo_emp@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.intruder_user = cls.env['res.users'].create({
            'name': 'Intruder',
            'login': 'ot_intruder',
            'email': 'ot_intruder@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
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
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Overtime Employee Emp',
            'user_id': cls.employee_user.id,
            'parent_id': cls.dept_manager.id,
        })
        cls.solo_manager = cls.env['hr.employee'].create({
            'name': 'Solo Manager Emp',
            'user_id': cls.single_dept_manager_user.id,
        })
        cls.solo_employee = cls.env['hr.employee'].create({
            'name': 'Solo Chain Employee Emp',
            'user_id': cls.solo_employee_user.id,
            'parent_id': cls.solo_manager.id,
        })

        cls.project = cls.env['project.project'].create({
            'name': 'Overtime Test Project',
            'allow_timesheets': True,
        })
        cls.task = cls.env['project.task'].create({
            'name': 'Overtime Test Task',
            'project_id': cls.project.id,
        })

        cls.env.ref('hr_overtime_management.group_overtime_hr_officer').write({
            'user_ids': [(4, cls.hr_officer.id)],
        })

        cls.env.company.write({
            'overtime_generate_analytic_line': False,
            'overtime_default_type_id': cls.regular_type.id,
        })

    def _dt(self, hour, minute=0, day_offset=0):
        base = datetime(2026, 7, 5, hour, minute, 0)
        if day_offset:
            base += timedelta(days=day_offset)
        return base

    def _create_request(self, employee=None, **kwargs):
        vals = {
            'employee_id': (employee or self.employee).id,
            'start_datetime': self._dt(18, 0),
            'end_datetime': self._dt(21, 0),
            'project_id': self.project.id,
            'task_id': self.task.id,
            'description': 'Test overtime',
        }
        vals.update(kwargs)
        return self.OvertimeRequest.create(vals)

    def _dt_on(self, year, month, day, hour, minute=0, end_hour=None, end_minute=0):
        start = datetime(year, month, day, hour, minute, 0)
        if end_hour is None:
            end = start + timedelta(hours=2)
        else:
            end_day = day
            if end_hour < hour:
                end_day += 1
            end = datetime(year, month, end_day, end_hour, end_minute, 0)
        return start, end

    def test_overtime_hours_same_day(self):
        request = self._create_request(
            start_datetime=self._dt(18, 0),
            end_datetime=self._dt(21, 30),
        )
        self.assertEqual(request.overtime_hours, 3.5)

    def test_overtime_hours_overnight(self):
        request = self._create_request(
            start_datetime=self._dt(22, 0),
            end_datetime=self._dt(2, 0, day_offset=1),
        )
        self.assertEqual(request.overtime_hours, 4.0)

    def test_chain_single_manager_two_stages(self):
        chain = self.ApprovalService.build_manager_hr_chain(self.solo_employee)
        roles = [role for role, _user in chain]
        self.assertEqual(roles, ['dept_manager', 'hr'])
        self.assertEqual(len(chain), 2)

    def test_chain_manager_upper_manager_three_stages(self):
        chain = self.ApprovalService.build_manager_hr_chain(self.employee)
        roles = [role for role, _user in chain]
        self.assertEqual(roles, ['dept_manager', 'upper_manager', 'hr'])
        self.assertEqual(chain[-1][0], 'hr')

    def test_chain_keeps_hr_when_same_user_as_manager(self):
        """HR stage must remain even if the HR officer is also the dept manager."""
        self.dept_manager_user.write({
            'group_ids': [(4, self.env.ref('hr_overtime_management.group_overtime_hr_officer').id)],
        })
        chain = self.ApprovalService.build_manager_hr_chain(self.employee)
        roles = [role for role, _user in chain]
        self.assertIn('hr', roles)
        self.assertEqual(roles[-1], 'hr')
        self.assertGreaterEqual(len(chain), 2)

    def test_refusal_at_stage_one_stops_chain(self):
        request = self._create_request(employee=self.employee)
        request.action_submit()
        self.assertEqual(len(request.approval_line_ids), 3)
        first_line = request.approval_line_ids.filtered(lambda l: l.state == 'to_approve')
        second_line = request.approval_line_ids.filtered(lambda l: l.role == 'upper_manager')
        request.with_user(self.dept_manager_user).action_process_refusal(first_line, 'Not approved')
        self.assertEqual(request.state, 'refused')
        self.assertEqual(first_line.state, 'refused')
        self.assertEqual(second_line.state, 'pending')
        self.assertFalse(request.approval_line_ids.filtered(lambda l: l.state == 'to_approve'))

    def test_non_approver_cannot_approve(self):
        request = self._create_request()
        request.action_submit()
        with self.assertRaises(AccessError):
            request.with_user(self.intruder_user).action_approve()

    def test_internal_user_has_overtime_group(self):
        self.assertTrue(
            self.employee_user.has_group('hr_overtime_management.group_overtime_user'),
            'Internal users should inherit overtime user group',
        )

    def test_employee_can_create_draft_without_approve(self):
        request = self.OvertimeRequest.with_user(self.employee_user).create({
            'start_datetime': self._dt(18, 0),
            'end_datetime': self._dt(21, 0),
            'project_id': self.project.id,
            'task_id': self.task.id,
            'description': 'Employee overtime',
        })
        self.assertEqual(request.employee_id, self.employee)
        self.assertEqual(request.company_id, self.employee.company_id)
        self.assertTrue(request.can_submit_request)
        self.assertFalse(request.can_approve_request)

    def test_employee_cannot_approve_submitted_request(self):
        request = self._create_request()
        request.action_submit()
        self.assertFalse(request.with_user(self.employee_user).can_approve_request)
        self.assertFalse(request.with_user(self.employee_user).can_refuse_request)

    def test_cross_company_project_requires_allowed_company(self):
        other_company = self.env['res.company'].create({'name': 'Other Overtime Co'})
        other_project = self.env['project.project'].create({
            'name': 'Other Company Project',
            'allow_timesheets': True,
            'company_id': other_company.id,
        })
        other_task = self.env['project.task'].create({
            'name': 'Other Task',
            'project_id': other_project.id,
            'allow_timesheets': True,
        })
        OvertimeAsEmployee = self.OvertimeRequest.with_user(self.employee_user)
        with self.assertRaises(UserError):
            OvertimeAsEmployee.create({
                'employee_id': self.employee.id,
                'start_datetime': self._dt(18, 0),
                'end_datetime': self._dt(21, 0),
                'project_id': other_project.id,
                'task_id': other_task.id,
                'description': 'Cross-company overtime',
            })
        self.employee_user.write({'company_ids': [(4, other_company.id)]})
        request = OvertimeAsEmployee.create({
            'employee_id': self.employee.id,
            'start_datetime': self._dt(18, 0),
            'end_datetime': self._dt(21, 0),
            'project_id': other_project.id,
            'task_id': other_task.id,
            'description': 'Cross-company overtime',
        })
        self.assertEqual(request.project_id, other_project)
        self.assertEqual(request.company_id, self.employee.company_id)

    def test_employee_sees_overtime_menu(self):
        menu = self.env['ir.ui.menu'].with_user(self.employee_user).search([
            ('name', 'ilike', 'Overtime'),
        ], limit=1)
        self.assertTrue(menu, 'Internal employee should see the Overtime app menu')

    def test_auto_overtime_type_weekday_regular(self):
        """Sunday (working day) should use regular overtime type."""
        start, end = self._dt_on(2026, 7, 5, 18, 0, 21, 0)
        request = self._create_request(start_datetime=start, end_datetime=end)
        self.assertEqual(request.overtime_type_id, self.regular_type)

    def test_auto_overtime_type_friday_weekend(self):
        start, end = self._dt_on(2026, 7, 3, 18, 0, 21, 0)
        request = self._create_request(start_datetime=start, end_datetime=end)
        self.assertEqual(request.overtime_type_id, self.weekend_type)

    def test_auto_overtime_type_saturday_weekend(self):
        start, end = self._dt_on(2026, 7, 4, 10, 0, 14, 0)
        request = self._create_request(start_datetime=start, end_datetime=end)
        self.assertEqual(request.overtime_type_id, self.weekend_type)

    def test_auto_overtime_type_public_holiday(self):
        calendar = self.employee.company_id.resource_calendar_id
        start, end = self._dt_on(2026, 7, 5, 9, 0, 12, 0)
        self.env['resource.calendar.leaves'].sudo().create({
            'name': 'Test Public Holiday',
            'calendar_id': calendar.id,
            'date_from': datetime(2026, 7, 5, 0, 0, 0),
            'date_to': datetime(2026, 7, 5, 23, 59, 59),
        })
        request = self._create_request(start_datetime=start, end_datetime=end)
        self.assertEqual(request.overtime_type_id, self.holiday_type)

    def test_cost_computation_all_types(self):
        hourly_cost = 100.0
        scenarios = [
            (self._dt_on(2026, 7, 5, 17, 0, 19, 0), self.regular_type, 1.5),
            (self._dt_on(2026, 7, 3, 17, 0, 19, 0), self.weekend_type, 2.0),
        ]
        calendar = self.employee.company_id.resource_calendar_id
        holiday_start, holiday_end = self._dt_on(2026, 7, 12, 17, 0, 19, 0)
        self.env['resource.calendar.leaves'].sudo().create({
            'name': 'Cost Test Holiday',
            'calendar_id': calendar.id,
            'date_from': datetime(2026, 7, 12, 0, 0, 0),
            'date_to': datetime(2026, 7, 12, 23, 59, 59),
        })
        scenarios.append((holiday_start, holiday_end, self.holiday_type, 2.5))
        with patch.object(
            type(self.env['hr.overtime.request']),
            '_get_hourly_cost_value',
            lambda self: hourly_cost,
        ):
            for start, end, ot_type, multiplier in scenarios:
                request = self._create_request(
                    start_datetime=start,
                    end_datetime=end,
                )
                self.assertEqual(request.overtime_type_id, ot_type)
                request._compute_hourly_cost()
                request._compute_total_cost()
                expected = 2.0 * hourly_cost * multiplier
                self.assertAlmostEqual(request.total_cost, expected, places=2)

    def test_full_approval_flow_three_stages(self):
        request = self._create_request()
        request.action_submit()
        request.with_user(self.dept_manager_user).action_approve()
        self.assertEqual(request.state, 'manager_approved')
        request.with_user(self.upper_manager_user).action_approve()
        self.assertEqual(request.state, 'upper_manager_approved')
        request.with_user(self.hr_officer).action_approve()
        self.assertEqual(request.state, 'hr_approved')

    def test_full_approval_flow_two_stages(self):
        request = self._create_request(employee=self.solo_employee)
        request.action_submit()
        self.assertEqual(len(request.approval_line_ids), 2)
        request.with_user(self.single_dept_manager_user).action_approve()
        self.assertEqual(request.state, 'manager_approved')
        request.with_user(self.hr_officer).action_approve()
        self.assertEqual(request.state, 'hr_approved')

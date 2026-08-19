# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date, datetime

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools.float_utils import float_compare


@tagged('post_install', '-at_install', 'hr_holidays_custom_ext')
class TestOvertimeTimeOff(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({
            'name': 'OT TimeOff Test Co',
        })
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'OT Test Calendar',
            'tz': 'Asia/Amman',
            'hours_per_day': 8.0,
            'attendance_ids': [
                (0, 0, {
                    'name': 'Morning',
                    'dayofweek': str(day),
                    'hour_from': 8.0,
                    'hour_to': 12.0,
                    'day_period': 'morning',
                })
                for day in range(6)
            ] + [
                (0, 0, {
                    'name': 'Afternoon',
                    'dayofweek': str(day),
                    'hour_from': 13.0,
                    'hour_to': 17.0,
                    'day_period': 'afternoon',
                })
                for day in range(6)
            ],
            'company_id': cls.company.id,
        })
        cls.company.resource_calendar_id = cls.calendar
        cls.employee = cls.env['hr.employee'].create({
            'name': 'OT Test Employee',
            'company_id': cls.company.id,
            'resource_calendar_id': cls.calendar.id,
        })
        leave_type = cls.env.ref(
            'hr_holidays_custom_ext.leave_type_overtime',
            raise_if_not_found=False,
        )
        if not leave_type:
            leave_type = cls.env['hr.leave.type'].create({
                'name': 'Overtime',
                'requires_allocation': True,
                'allocation_validation_type': 'no_validation',
                'leave_validation_type': 'manager',
                'request_unit': 'hour',
            })
        cls.leave_type = leave_type
        cls.company.overtime_leave_type_id = leave_type
        cls.Allocation = cls.env['hr.leave.allocation'].sudo()
        cls.Helper = cls.env['hr.overtime.leave.helper']

    def test_create_overtime_allocation(self):
        alloc = self.Helper.create_overtime_allocation(
            employee=self.employee,
            hours=2.0,
            origin='overtime_request',
        )
        self.assertTrue(alloc)
        self.assertEqual(alloc.state, 'validate')
        self.assertEqual(alloc.allocation_origin, 'overtime_request')
        expected_days = 2.0 / 8.0
        self.assertAlmostEqual(alloc.number_of_days, expected_days, places=2)

    def test_reverse_allocation_works_when_unused(self):
        alloc = self.Helper.create_overtime_allocation(
            employee=self.employee,
            hours=1.5,
            origin='attendance_extra',
        )
        result = self.Helper.reverse_overtime_allocation(alloc)
        self.assertTrue(result)
        self.assertEqual(alloc.state, 'refuse')

    def test_duplicate_ot_approval_is_idempotent(self):
        project = self.env['project.project'].create({
            'name': 'OT Test Project',
            'company_id': self.company.id,
            'allow_timesheets': True,
        })
        task = self.env['project.task'].create({
            'name': 'OT Test Task',
            'project_id': project.id,
        })
        OTRequest = self.env['hr.overtime.request'].sudo()
        request = OTRequest.create({
            'employee_id': self.employee.id,
            'start_datetime': datetime(2026, 8, 10, 17, 0),
            'end_datetime': datetime(2026, 8, 10, 19, 0),
            'description': 'Test OT',
            'project_id': project.id,
            'task_id': task.id,
        })
        request._on_approval_complete()
        allocs1 = self.Allocation.search([
            ('overtime_request_id', '=', request.id),
        ])
        self.assertEqual(len(allocs1), 1)
        request._on_approval_complete()
        allocs2 = self.Allocation.search([
            ('overtime_request_id', '=', request.id),
        ])
        self.assertEqual(len(allocs2), 1)

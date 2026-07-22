# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'hr_holidays_custom_ext')
class TestLeaveBalanceSummary(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Balance Test Employee',
            'company_id': cls.env.company.id,
        })
        cls.leave_type = cls.env['hr.leave.type'].create({
            'name': 'Annual Balance Test',
            'requires_allocation': True,
            'request_unit': 'day',
            'company_id': cls.env.company.id,
        })
        cls.allocation = cls.env['hr.leave.allocation'].create({
            'name': 'Annual Allocation',
            'employee_id': cls.employee.id,
            'holiday_status_id': cls.leave_type.id,
            'allocation_type': 'regular',
            'number_of_days': 14,
            'date_from': '2026-01-01',
        })
        cls.allocation.sudo().action_approve()

    def test_balance_summary_matches_allocation_data(self):
        as_of_date = '2026-07-01'
        allocation_data = self.leave_type.get_allocation_data(
            self.employee,
            as_of_date,
        )[self.employee][0][1]

        summary = self.env['hr.leave.balance.summary'].rebuild_summary(
            as_of_date=as_of_date,
            company_id=self.env.company.id,
            leave_type_id=self.leave_type.id,
        )
        row = summary.filtered(
            lambda line: line.employee_id == self.employee
            and line.leave_type_id == self.leave_type
        )
        self.assertEqual(len(row), 1)
        self.assertEqual(row.total_accrued, allocation_data['max_leaves'])
        self.assertEqual(row.days_used, allocation_data['leaves_taken'])
        self.assertEqual(row.days_remaining, allocation_data['remaining_leaves'])
        self.assertEqual(row.total_available, allocation_data['virtual_remaining_leaves'])

# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'hr_loans_advances')
class TestHrEmployeeAdvance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Advance = cls.env['hr.employee.advance']

        cls.hr_user = cls.env['res.users'].create({
            'name': 'Loans HR Officer',
            'login': 'la_hr_officer',
            'email': 'la_hr_officer@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('hr.group_hr_user').id,
                cls.env.ref('hr_loans_advances.group_loans_advances_hr_officer').id,
            ])],
        })
        cls.manager_user = cls.env['res.users'].create({
            'name': 'Loans Manager',
            'login': 'la_manager',
            'email': 'la_manager@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.employee_user = cls.env['res.users'].create({
            'name': 'Loans Employee',
            'login': 'la_employee',
            'email': 'la_employee@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

        cls.manager = cls.env['hr.employee'].create({
            'name': 'Loans Manager Emp',
            'user_id': cls.manager_user.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Loans Employee Emp',
            'user_id': cls.employee_user.id,
            'parent_id': cls.manager.id,
        })

    def _create_advance(self, amount=500.0):
        return self.Advance.create({
            'employee_id': self.employee.id,
            'request_date': date(2026, 7, 1),
            'amount': amount,
            'reason': 'Emergency advance',
        })

    def test_advance_approval_flow(self):
        advance = self._create_advance()
        self.assertEqual(advance.state, 'draft')
        self.assertEqual(advance.amount_remaining, 500.0)

        advance.with_user(self.employee_user).action_submit()
        self.assertEqual(advance.state, 'submitted')
        self.assertEqual(len(advance.approval_line_ids), 2)

        advance.with_user(self.manager_user).action_approve()
        self.assertEqual(advance.state, 'manager_approved')

        advance.with_user(self.hr_user).action_approve()
        self.assertEqual(advance.state, 'hr_approved')
        self.assertEqual(advance.amount_remaining, 500.0)

    def test_advance_full_repayment_sets_repaid(self):
        advance = self._create_advance(amount=300.0)
        advance.with_user(self.employee_user).action_submit()
        advance.with_user(self.manager_user).action_approve()
        advance.with_user(self.hr_user).action_approve()

        advance.register_repayment(300.0, repayment_date=date(2026, 8, 1))
        self.assertEqual(advance.amount_repaid, 300.0)
        self.assertEqual(advance.amount_remaining, 0.0)
        self.assertEqual(advance.state, 'repaid')
        self.assertEqual(len(advance.repayment_ids), 1)

    def test_advance_repayment_never_negative(self):
        advance = self._create_advance(amount=200.0)
        advance.with_user(self.employee_user).action_submit()
        advance.with_user(self.manager_user).action_approve()
        advance.with_user(self.hr_user).action_approve()

        advance.register_repayment(100.0, repayment_date=date(2026, 8, 1))
        with self.assertRaises(UserError):
            advance.register_repayment(150.0, repayment_date=date(2026, 9, 1))
        self.assertEqual(advance.amount_remaining, 100.0)
        self.assertGreaterEqual(advance.amount_remaining, 0.0)

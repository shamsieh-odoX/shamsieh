# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'hr_loans_advances')
class TestHrEmployeeLoan(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Loan = cls.env['hr.employee.loan']

        cls.hr_user = cls.env['res.users'].create({
            'name': 'Loan HR Officer',
            'login': 'loan_hr_officer',
            'email': 'loan_hr_officer@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('hr.group_hr_user').id,
                cls.env.ref('hr_loans_advances.group_loans_advances_hr_officer').id,
            ])],
        })
        cls.manager_user = cls.env['res.users'].create({
            'name': 'Loan Manager',
            'login': 'loan_manager',
            'email': 'loan_manager@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.upper_manager_user = cls.env['res.users'].create({
            'name': 'Loan Upper Manager',
            'login': 'loan_upper_manager',
            'email': 'loan_upper_manager@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.employee_user = cls.env['res.users'].create({
            'name': 'Loan Employee',
            'login': 'loan_employee',
            'email': 'loan_employee@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

        cls.upper_manager = cls.env['hr.employee'].create({
            'name': 'Loan Upper Manager Emp',
            'user_id': cls.upper_manager_user.id,
        })
        cls.manager = cls.env['hr.employee'].create({
            'name': 'Loan Manager Emp',
            'user_id': cls.manager_user.id,
            'parent_id': cls.upper_manager.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Loan Employee Emp',
            'user_id': cls.employee_user.id,
            'parent_id': cls.manager.id,
        })

    def _create_loan(self, total=1200.0, installment=300.0):
        return self.Loan.create({
            'employee_id': self.employee.id,
            'total_amount': total,
            'monthly_installment': installment,
            'deduction_start_date': date(2026, 1, 1),
            'deduction_end_date': date(2026, 12, 31),
        })

    def _approve_loan(self, loan):
        loan.with_user(self.employee_user).action_submit()
        loan.with_user(self.manager_user).action_approve()
        self.assertEqual(loan.state, 'manager_approved')
        loan.with_user(self.upper_manager_user).action_approve()
        self.assertEqual(loan.state, 'upper_manager_approved')
        loan.with_user(self.hr_user).action_approve()

    def test_loan_three_step_approval_chain(self):
        loan = self._create_loan()
        loan.with_user(self.employee_user).action_submit()
        roles = loan.approval_line_ids.mapped('role')
        self.assertEqual(roles, ['dept_manager', 'upper_manager', 'hr'])
        self._approve_loan(loan)
        self.assertEqual(loan.state, 'hr_approved')

    def test_loan_creation(self):
        loan = self._create_loan()
        self.assertTrue(loan.name.startswith('LOAN/'))
        self.assertEqual(loan.state, 'draft')
        self.assertEqual(loan.amount_paid, 0.0)
        self.assertEqual(loan.amount_remaining, 1200.0)

    def test_monthly_deduction_reduces_balance(self):
        loan = self._create_loan(total=900.0, installment=300.0)
        self._approve_loan(loan)
        self.assertEqual(loan.state, 'hr_approved')

        self.assertTrue(loan.apply_monthly_deduction(date(2026, 3, 15)))
        self.assertTrue(loan.apply_monthly_deduction(date(2026, 4, 10)))
        self.assertTrue(loan.apply_monthly_deduction(date(2026, 5, 20)))

        self.assertEqual(loan.amount_paid, 900.0)
        self.assertEqual(loan.amount_remaining, 0.0)
        self.assertEqual(loan.state, 'done')
        self.assertEqual(len(loan.payment_ids), 3)

    def test_monthly_deduction_idempotent(self):
        loan = self._create_loan(total=600.0, installment=200.0)
        self._approve_loan(loan)

        self.assertTrue(loan.apply_monthly_deduction(date(2026, 6, 1)))
        self.assertFalse(loan.apply_monthly_deduction(date(2026, 6, 20)))
        self.assertEqual(loan.amount_paid, 200.0)
        self.assertEqual(len(loan.payment_ids), 1)

    def test_loan_balance_never_negative(self):
        loan = self._create_loan(total=500.0, installment=100.0)
        self._approve_loan(loan)

        loan.register_payment(400.0, payment_date=date(2026, 2, 1))
        with self.assertRaises(UserError):
            loan.register_payment(200.0, payment_date=date(2026, 3, 1))
        self.assertEqual(loan.amount_remaining, 100.0)
        self.assertGreaterEqual(loan.amount_remaining, 0.0)

    def test_monthly_deduction_caps_final_installment(self):
        loan = self._create_loan(total=500.0, installment=300.0)
        self._approve_loan(loan)

        loan.apply_monthly_deduction(date(2026, 7, 1))
        loan.apply_monthly_deduction(date(2026, 8, 1))
        self.assertEqual(loan.amount_paid, 500.0)
        self.assertEqual(loan.amount_remaining, 0.0)
        self.assertEqual(loan.state, 'done')
        self.assertEqual(loan.payment_ids[-1].amount, 200.0)

    def test_employee_can_request_loan_without_company_acl(self):
        """Employees do not need read access to every company to request a loan."""
        other_company = self.env['res.company'].create({'name': 'Loan Branch Co'})
        self.employee.company_id = other_company
        Loan = self.Loan.with_user(self.employee_user).with_context(
            allowed_company_ids=self.employee_user.company_ids.ids,
        )
        Loan.default_get([
            'employee_id', 'company_id', 'currency_id',
            'total_amount', 'monthly_installment',
        ])
        loan = Loan.create({
            'employee_id': self.employee.id,
            'total_amount': 1000.0,
            'monthly_installment': 100.0,
            'deduction_start_date': date(2026, 1, 1),
            'deduction_end_date': date(2026, 12, 31),
        })
        self.assertEqual(loan.company_id, other_company)
        loan.web_read({
            'name': {},
            'company_id': {},
            'currency_id': {},
            'employee_id': {},
        })
        loan.action_submit()
        self.assertEqual(loan.state, 'submitted')

# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.hr_payroll_jo_custom_ext.hooks import get_jordan_payroll_structure


@tagged('post_install', '-at_install', 'hr_payroll_jo')
class TestJordanPayslipIntegration(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'hr.payslip' not in cls.env:
            cls.skipTest(cls, 'Payroll is not installed.')
        cls.structure = get_jordan_payroll_structure(cls.env)
        if not cls.structure:
            cls.skipTest(cls, 'Jordan payroll structure is not available.')

        cls.company = cls.env.company
        cls.company.write({
            'payroll_daily_wage_divisor': 30,
            'payroll_absence_deduction_enabled': True,
        })

        cls.hr_user = cls.env['res.users'].create({
            'name': 'Jordan Payroll HR',
            'login': 'jo_payroll_hr',
            'email': 'jo_payroll_hr@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('hr.group_hr_user').id,
                cls.env.ref('hr_payroll.group_hr_payroll_user').id,
            ])],
        })
        cls.manager_user = cls.env['res.users'].create({
            'name': 'Jordan Payroll Manager',
            'login': 'jo_payroll_manager',
            'email': 'jo_payroll_manager@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.employee_user = cls.env['res.users'].create({
            'name': 'Jordan Payroll Employee',
            'login': 'jo_payroll_employee',
            'email': 'jo_payroll_employee@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

        cls.manager = cls.env['hr.employee'].create({
            'name': 'Jordan Manager',
            'user_id': cls.manager_user.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Jordan Employee',
            'user_id': cls.employee_user.id,
            'parent_id': cls.manager.id,
        })
        cls._create_contract(cls.employee, wage=3000.0)

        cls.loans_hr_user = cls.env['res.users'].create({
            'name': 'Jordan Loans HR',
            'login': 'jo_loans_hr',
            'email': 'jo_loans_hr@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('hr.group_hr_user').id,
                cls.env.ref('hr_loans_advances.group_loans_advances_hr_officer').id,
            ])],
        })

    @classmethod
    def _create_contract(cls, employee, wage=3000.0):
        contract_model = 'hr.version' if 'hr.version' in cls.env else 'hr.contract'
        contract_vals = {
            'name': 'Jordan Contract',
            'employee_id': employee.id,
            'wage': wage,
            'date_start': date(2026, 1, 1),
        }
        if contract_model == 'hr.contract':
            contract_vals['structure_type_id'] = cls.structure.type_id.id
            if 'struct_id' in cls.env[contract_model]._fields:
                contract_vals['struct_id'] = cls.structure.id
            elif 'structure_id' in cls.env[contract_model]._fields:
                contract_vals['structure_id'] = cls.structure.id
        else:
            if 'structure_type_id' in cls.env[contract_model]._fields:
                contract_vals['structure_type_id'] = cls.structure.type_id.id
            if 'structure_id' in cls.env[contract_model]._fields:
                contract_vals['structure_id'] = cls.structure.id
        return cls.env[contract_model].create(contract_vals)

    def _create_payslip(self, employee=None, date_from=None, date_to=None):
        employee = employee or self.employee
        date_from = date_from or date(2026, 7, 1)
        date_to = date_to or date(2026, 7, 31)
        contract = (
            payslip.contract_id
            or getattr(employee, 'version_id', False)
            or getattr(employee, 'contract_id', False)
        )
        payslip_vals = {
            'employee_id': employee.id,
            'date_from': date_from,
            'date_to': date_to,
            'name': 'Jordan Test Payslip',
        }
        if contract:
            if 'contract_id' in self.env['hr.payslip']._fields:
                payslip_vals['contract_id'] = contract.id
            if 'version_id' in self.env['hr.payslip']._fields:
                payslip_vals['version_id'] = contract.id
        if 'struct_id' in self.env['hr.payslip']._fields:
            payslip_vals['struct_id'] = self.structure.id
        return self.env['hr.payslip'].create(payslip_vals)

    def _input_amount(self, payslip, code):
        lines = payslip.input_line_ids.filtered(
            lambda line: line.input_type_id.code == code
        )
        return sum(lines.mapped('amount'))

    def _line_total(self, payslip, code):
        lines = payslip.line_ids.filtered(lambda line: line.code == code)
        return sum(lines.mapped('total'))

    def test_payslip_no_deductions(self):
        payslip = self._create_payslip()
        payslip.compute_sheet()

        self.assertEqual(self._input_amount(payslip, 'ABSENCE'), 0.0)
        self.assertEqual(self._input_amount(payslip, 'UNPAID'), 0.0)
        self.assertEqual(self._input_amount(payslip, 'LOAN'), 0.0)
        self.assertEqual(self._input_amount(payslip, 'ADVANCE'), 0.0)
        self.assertEqual(payslip.jo_absence_days, 0.0)
        self.assertEqual(payslip.jo_unpaid_leave_days, 0.0)

        absence_line = self._line_total(payslip, 'ABSENCE')
        unpaid_line = self._line_total(payslip, 'UNPAID')
        loan_line = self._line_total(payslip, 'LOAN')
        advance_line = self._line_total(payslip, 'ADVANCE')
        self.assertEqual(absence_line, 0.0)
        self.assertEqual(unpaid_line, 0.0)
        self.assertEqual(loan_line, 0.0)
        self.assertEqual(advance_line, 0.0)

    def test_payslip_unpaid_leave_and_absence(self):
        self.env['hr.attendance.daily.status'].create([
            {
                'employee_id': self.employee.id,
                'date': date(2026, 7, 7),
                'status': 'absent',
            },
            {
                'employee_id': self.employee.id,
                'date': date(2026, 7, 8),
                'status': 'absent',
            },
        ])

        unpaid_type = self.env['hr.leave.type'].search([('unpaid', '=', True)], limit=1)
        if not unpaid_type:
            unpaid_type = self.env['hr.leave.type'].create({
                'name': 'Unpaid Test Leave',
                'requires_allocation': 'no',
                'leave_validation_type': 'hr',
                'unpaid': True,
            })

        leave = self.env['hr.leave'].create({
            'name': 'Unpaid day',
            'employee_id': self.employee.id,
            'holiday_status_id': unpaid_type.id,
            'request_date_from': date(2026, 7, 15),
            'request_date_to': date(2026, 7, 15),
        })
        leave.action_validate()

        payslip = self._create_payslip()
        payslip.compute_sheet()

        daily_rate = 3000.0 / 30.0
        self.assertEqual(payslip.jo_absence_days, 2.0)
        self.assertGreaterEqual(payslip.jo_unpaid_leave_days, 1.0)
        self.assertAlmostEqual(self._input_amount(payslip, 'ABSENCE'), 2.0 * daily_rate, places=2)
        self.assertAlmostEqual(self._input_amount(payslip, 'UNPAID'), daily_rate, places=2)
        self.assertLess(self._line_total(payslip, 'ABSENCE'), 0.0)
        self.assertLess(self._line_total(payslip, 'UNPAID'), 0.0)

    def test_payslip_active_loan_installment(self):
        loan = self.env['hr.employee.loan'].create({
            'employee_id': self.employee.id,
            'total_amount': 1200.0,
            'monthly_installment': 300.0,
            'deduction_start_date': date(2026, 1, 1),
            'deduction_end_date': date(2026, 12, 31),
        })
        loan.with_user(self.employee_user).action_submit()
        loan.with_user(self.manager_user).action_approve()
        loan.with_user(self.loans_hr_user).action_approve()
        self.assertEqual(loan.state, 'hr_approved')

        payslip = self._create_payslip()
        payslip.compute_sheet()
        self.assertEqual(self._input_amount(payslip, 'LOAN'), 300.0)
        self.assertEqual(self._line_total(payslip, 'LOAN'), -300.0)

        payslip.action_payslip_done()
        self.assertTrue(payslip.jo_deductions_posted)
        self.assertEqual(loan.amount_paid, 300.0)
        self.assertEqual(loan.amount_remaining, 900.0)
        payment = loan.payment_ids.filtered(lambda p: p.payslip_id == payslip)
        self.assertEqual(len(payment), 1)
        self.assertEqual(payment.source, 'payslip')

        payslip.action_payslip_cancel()
        self.assertFalse(payslip.jo_deductions_posted)
        self.assertEqual(loan.amount_paid, 0.0)
        self.assertEqual(loan.amount_remaining, 1200.0)

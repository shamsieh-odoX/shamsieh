# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from datetime import date

from odoo import _, models

_logger = logging.getLogger(__name__)

DEFAULT_MONTHLY_HOURS = 173.33

INPUT_TYPES = (
    ('UNWORKED_DEDUCTION', 'Unworked Time Deduction'),
    ('LOAN_DEDUCTION', 'Loan Installment'),
    ('ADVANCE_DEDUCTION', 'Salary Advance Recovery'),
)

RULE_DEFINITIONS = (
    {
        'code': 'UNWORKED_DED',
        'name': 'Unworked Time Deduction',
        'sequence': 150,
        'input_code': 'UNWORKED_DEDUCTION',
    },
    {
        'code': 'LOAN_DED',
        'name': 'Loan Installment',
        'sequence': 160,
        'input_code': 'LOAN_DEDUCTION',
    },
    {
        'code': 'ADV_DED',
        'name': 'Salary Advance Recovery',
        'sequence': 170,
        'input_code': 'ADVANCE_DEDUCTION',
    },
)


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # ------------------------------------------------------------------
    # Lazy setup (avoids fragile XML external IDs on install/upgrade)
    # ------------------------------------------------------------------

    def _ensure_payroll_custom_setup(self):
        """Best-effort create input types + salary rules if missing."""
        try:
            self._ensure_input_types()
            self._ensure_salary_rules()
        except Exception:
            _logger.exception(
                'hr_payroll_custom_ext: setup of input types/rules failed'
            )

    def _ensure_input_types(self):
        InputType = self.env['hr.payslip.input.type'].sudo()
        for code, name in INPUT_TYPES:
            existing = InputType.search([('code', '=', code)], limit=1)
            if not existing:
                InputType.create({'name': name, 'code': code})

    def _ensure_salary_rules(self):
        Category = self.env['hr.salary.rule.category'].sudo()
        category = Category.search([('code', '=', 'CUSTOM_DED')], limit=1)
        if not category:
            vals = {'name': 'Custom Deductions', 'code': 'CUSTOM_DED'}
            parent = self.env.ref('hr_payroll.DED', raise_if_not_found=False)
            if parent:
                vals['parent_id'] = parent.id
            category = Category.create(vals)

        Structure = self.env['hr.payroll.structure'].sudo()
        structures = Structure.search([])
        if not structures:
            return

        Rule = self.env['hr.salary.rule'].sudo()
        for structure in structures:
            for definition in RULE_DEFINITIONS:
                existing = Rule.search([
                    ('struct_id', '=', structure.id),
                    ('code', '=', definition['code']),
                ], limit=1)
                input_code = definition['input_code']
                vals = {
                    'name': definition['name'],
                    'code': definition['code'],
                    'sequence': definition['sequence'],
                    'category_id': category.id,
                    'struct_id': structure.id,
                    'condition_select': 'python',
                    'condition_python': "result = inputs.get('%s', 0)" % input_code,
                    'amount_select': 'code',
                    'amount_python_compute': (
                        "result = -(inputs.get('%s') or 0)" % input_code
                    ),
                    'active': True,
                }
                if existing:
                    existing.write(vals)
                else:
                    Rule.create(vals)

    # ------------------------------------------------------------------
    # Input auto-population
    # ------------------------------------------------------------------

    def compute_sheet(self):
        self._ensure_payroll_custom_setup()
        self._sync_custom_deduction_inputs()
        return super().compute_sheet()

    def _sync_custom_deduction_inputs(self):
        for payslip in self:
            if not payslip.employee_id or not payslip.date_from or not payslip.date_to:
                continue
            for code, amount, description in payslip._get_custom_deduction_inputs():
                payslip._upsert_input_line(code, amount, description)

    def _get_custom_deduction_inputs(self):
        self.ensure_one()
        result = []
        result += self._get_unworked_deduction_input()
        result += self._get_loan_deduction_input()
        result += self._get_advance_deduction_input()
        return result

    def _get_input_type(self, code):
        return self.env['hr.payslip.input.type'].search([('code', '=', code)], limit=1)

    def _upsert_input_line(self, code, amount, label):
        self.ensure_one()
        input_type = self._get_input_type(code)
        if not input_type:
            _logger.warning('Payslip input type %s not found; skipping.', code)
            return
        amount = round(float(amount or 0.0), 2)
        existing = self.input_line_ids.filtered(
            lambda line: line.input_type_id.code == code
        )
        if amount <= 0:
            existing.unlink()
            return
        vals = {
            'name': label,
            'amount': amount,
            'input_type_id': input_type.id,
        }
        if existing:
            existing.write(vals)
        else:
            self.env['hr.payslip.input'].create({
                **vals,
                'payslip_id': self.id,
            })

    def _get_unworked_deduction_input(self):
        self.ensure_one()
        if 'hr.attendance.daily.status' not in self.env:
            return []
        DailyStatus = self.env['hr.attendance.daily.status'].sudo()
        statuses = DailyStatus.search([
            ('employee_id', '=', self.employee_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ])
        total_unworked = sum(statuses.mapped('unworked_minutes'))
        if total_unworked <= 0:
            return []
        contract = self.contract_id
        if not contract:
            return []
        hours_per_month = getattr(contract, 'hours_per_month', None) or DEFAULT_MONTHLY_HOURS
        if not hours_per_month:
            hours_per_month = DEFAULT_MONTHLY_HOURS
        hourly_rate = contract.wage / hours_per_month
        amount = round((total_unworked / 60.0) * hourly_rate, 2)
        return [('UNWORKED_DEDUCTION', amount, _('Unworked: %d min') % total_unworked)]

    def _loan_has_payment_for_period(self, loan):
        as_of = self.date_to
        month_start = date(as_of.year, as_of.month, 1)
        if as_of.month == 12:
            month_end = date(as_of.year + 1, 1, 1)
        else:
            month_end = date(as_of.year, as_of.month + 1, 1)
        return bool(loan.payment_ids.filtered(
            lambda payment: payment.source in ('monthly', 'payslip')
            and month_start <= payment.date < month_end
        ))

    def _get_loan_deduction_input(self):
        self.ensure_one()
        if 'hr.employee.loan' not in self.env:
            return []
        Loan = self.env['hr.employee.loan'].sudo()
        loans = Loan.search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'hr_approved'),
            ('amount_remaining', '>', 0),
            ('deduction_start_date', '<=', self.date_to),
            ('deduction_end_date', '>=', self.date_from),
        ])
        total = 0.0
        for loan in loans:
            if self._loan_has_payment_for_period(loan):
                continue
            total += min(loan.monthly_installment, loan.amount_remaining)
        if total <= 0:
            return []
        return [('LOAN_DEDUCTION', round(total, 2), _('Loan installments'))]

    def _get_advance_deduction_input(self):
        self.ensure_one()
        if 'hr.employee.advance' not in self.env:
            return []
        Advance = self.env['hr.employee.advance'].sudo()
        advances = Advance.search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'hr_approved'),
            ('deduct_from_next_payslip', '=', True),
            ('amount_remaining', '>', 0),
        ])
        total = sum(advances.mapped('amount_remaining'))
        if total <= 0:
            return []
        return [('ADVANCE_DEDUCTION', round(total, 2), _('Advance recovery'))]

    # ------------------------------------------------------------------
    # Auto-register loan / advance payments on payslip confirmation
    # ------------------------------------------------------------------

    def action_payslip_done(self):
        res = super().action_payslip_done()
        for payslip in self:
            try:
                payslip._register_loan_payments()
                payslip._register_advance_repayments()
            except Exception:
                _logger.exception(
                    'hr_payroll_custom_ext: failed posting loan/advance for payslip %s',
                    payslip.id,
                )
        return res

    def _get_input_amount_by_code(self, code):
        self.ensure_one()
        lines = self.input_line_ids.filtered(lambda line: line.input_type_id.code == code)
        return abs(sum(lines.mapped('amount')))

    def _register_loan_payments(self):
        self.ensure_one()
        deducted = self._get_input_amount_by_code('LOAN_DEDUCTION')
        if deducted <= 0 or 'hr.employee.loan' not in self.env:
            return
        Loan = self.env['hr.employee.loan'].sudo()
        loans = Loan.search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'hr_approved'),
            ('amount_remaining', '>', 0),
            ('deduction_start_date', '<=', self.date_to),
            ('deduction_end_date', '>=', self.date_from),
        ])
        remaining_to_distribute = deducted
        for loan in loans:
            if remaining_to_distribute <= 0:
                break
            if self._loan_has_payment_for_period(loan):
                continue
            amount = min(loan.monthly_installment, loan.amount_remaining, remaining_to_distribute)
            if amount > 0:
                loan.register_payment(amount, payment_date=self.date_to, source='payslip')
                remaining_to_distribute -= amount

    def _register_advance_repayments(self):
        self.ensure_one()
        deducted = self._get_input_amount_by_code('ADVANCE_DEDUCTION')
        if deducted <= 0 or 'hr.employee.advance' not in self.env:
            return
        Advance = self.env['hr.employee.advance'].sudo()
        advances = Advance.search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'hr_approved'),
            ('deduct_from_next_payslip', '=', True),
            ('amount_remaining', '>', 0),
        ])
        remaining_to_distribute = deducted
        for advance in advances:
            if remaining_to_distribute <= 0:
                break
            amount = min(advance.amount_remaining, remaining_to_distribute)
            if amount > 0:
                advance.register_repayment(amount, repayment_date=self.date_to, source='payslip')
                remaining_to_distribute -= amount

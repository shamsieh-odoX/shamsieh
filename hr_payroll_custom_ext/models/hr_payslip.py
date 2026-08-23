# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from datetime import date

from odoo import _, api, models

_logger = logging.getLogger(__name__)

DEFAULT_MONTHLY_HOURS = 173.33


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # ------------------------------------------------------------------
    # Input auto-population
    # ------------------------------------------------------------------

    def _get_custom_deduction_inputs(self):
        """Return a list of (input_type_code, amount, description) tuples."""
        self.ensure_one()
        result = []
        result += self._get_unworked_deduction_input()
        result += self._get_loan_deduction_input()
        result += self._get_advance_deduction_input()
        return result

    def _get_unworked_deduction_input(self):
        self.ensure_one()
        if not self.employee_id or not self.date_from or not self.date_to:
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
        hourly_rate = contract.wage / hours_per_month
        amount = round((total_unworked / 60.0) * hourly_rate, 2)
        return [('UNWORKED_DEDUCTION', amount, _('Unworked: %d min') % total_unworked)]

    def _get_loan_deduction_input(self):
        self.ensure_one()
        if not self.employee_id or not self.date_from or not self.date_to:
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
            if not loan._has_monthly_payment_for(self.date_to):
                total += min(loan.monthly_installment, loan.amount_remaining)
        if total <= 0:
            return []
        return [('LOAN_DEDUCTION', round(total, 2), _('Loan installments'))]

    def _get_advance_deduction_input(self):
        self.ensure_one()
        if not self.employee_id:
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

    def _get_input_lines(self):
        """Extend standard input lines with custom deductions."""
        res = super()._get_input_lines()
        InputType = self.env['hr.payslip.input.type']
        for payslip in self:
            custom_inputs = payslip._get_custom_deduction_inputs()
            for code, amount, description in custom_inputs:
                input_type = InputType.search([('code', '=', code)], limit=1)
                if not input_type:
                    _logger.warning('Payslip input type %s not found; skipping.', code)
                    continue
                existing = [
                    line for line in res
                    if line.get('input_type_id') == input_type.id
                    and line.get('payslip_id') == payslip.id
                ]
                if existing:
                    existing[0]['amount'] = amount
                    existing[0]['name'] = description
                else:
                    res.append({
                        'payslip_id': payslip.id,
                        'input_type_id': input_type.id,
                        'amount': amount,
                        'name': description,
                    })
        return res

    # ------------------------------------------------------------------
    # Auto-register loan / advance payments on payslip confirmation
    # ------------------------------------------------------------------

    def action_payslip_done(self):
        res = super().action_payslip_done()
        for payslip in self:
            payslip._register_loan_payments()
            payslip._register_advance_repayments()
        return res

    def _get_line_amount_by_code(self, code):
        """Return the absolute deducted amount for a salary rule code."""
        self.ensure_one()
        line = self.line_ids.filtered(lambda l: l.code == code)
        if line:
            return abs(line[0].total)
        return 0.0

    def _register_loan_payments(self):
        self.ensure_one()
        deducted = self._get_line_amount_by_code('LOAN_DED')
        if deducted <= 0:
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
            if loan._has_monthly_payment_for(self.date_to):
                continue
            amount = min(loan.monthly_installment, loan.amount_remaining, remaining_to_distribute)
            if amount > 0:
                loan.register_payment(amount, payment_date=self.date_to, source='payslip')
                remaining_to_distribute -= amount

    def _register_advance_repayments(self):
        self.ensure_one()
        deducted = self._get_line_amount_by_code('ADV_DED')
        if deducted <= 0:
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

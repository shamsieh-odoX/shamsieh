# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from datetime import date

from odoo import _, models

_logger = logging.getLogger(__name__)

DEFAULT_MONTHLY_HOURS = 173.33


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # ------------------------------------------------------------------
    # Input auto-population (Odoo 19: sync on compute_sheet)
    # ------------------------------------------------------------------

    def compute_sheet(self):
        self._sync_custom_deduction_inputs()
        return super().compute_sheet()

    def _sync_custom_deduction_inputs(self):
        for payslip in self:
            if not payslip.employee_id or not payslip.date_from or not payslip.date_to:
                continue
            for code, amount, description in payslip._get_custom_deduction_inputs():
                payslip._upsert_input_line(code, amount, description)

    def _get_custom_deduction_inputs(self):
        """Return a list of (input_type_code, amount, description) tuples."""
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
        """True if loan already has a monthly/payslip payment covering this payslip month."""
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
            payslip._register_loan_payments()
            payslip._register_advance_repayments()
        return res

    def _get_input_amount_by_code(self, code):
        self.ensure_one()
        lines = self.input_line_ids.filtered(lambda line: line.input_type_id.code == code)
        return abs(sum(lines.mapped('amount')))

    def _register_loan_payments(self):
        self.ensure_one()
        deducted = self._get_input_amount_by_code('LOAN_DEDUCTION')
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
            if self._loan_has_payment_for_period(loan):
                continue
            amount = min(loan.monthly_installment, loan.amount_remaining, remaining_to_distribute)
            if amount > 0:
                loan.register_payment(amount, payment_date=self.date_to, source='payslip')
                remaining_to_distribute -= amount

    def _register_advance_repayments(self):
        self.ensure_one()
        deducted = self._get_input_amount_by_code('ADVANCE_DEDUCTION')
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

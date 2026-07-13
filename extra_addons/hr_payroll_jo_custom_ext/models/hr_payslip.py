# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    jo_absence_days = fields.Float(
        string='Absence Days',
        compute='_compute_jo_payroll_metrics',
        store=True,
        readonly=True,
    )
    jo_unpaid_leave_days = fields.Float(
        string='Unpaid Leave Days',
        compute='_compute_jo_payroll_metrics',
        store=True,
        readonly=True,
    )
    jo_loan_installment = fields.Monetary(
        string='Loan Installment',
        compute='_compute_jo_payroll_metrics',
        store=True,
        currency_field='currency_id',
        readonly=True,
    )
    jo_advance_deduction = fields.Monetary(
        string='Advance Deduction',
        compute='_compute_jo_payroll_metrics',
        store=True,
        currency_field='currency_id',
        readonly=True,
    )
    jo_overtime_amount = fields.Monetary(
        string='Overtime Amount',
        compute='_compute_jo_payroll_metrics',
        store=True,
        currency_field='currency_id',
        readonly=True,
    )
    jo_deductions_posted = fields.Boolean(
        string='Loan/Advance Deductions Posted',
        copy=False,
        readonly=True,
    )

    @api.depends(
        'employee_id',
        'date_from',
        'date_to',
        'contract_id',
        'contract_id.wage',
        'company_id.payroll_daily_wage_divisor',
        'company_id.payroll_absence_deduction_enabled',
        'input_line_ids.amount',
        'input_line_ids.input_type_id.code',
    )
    def _compute_jo_payroll_metrics(self):
        for payslip in self:
            metrics = payslip._collect_jordan_payroll_metrics()
            payslip.jo_absence_days = metrics['absence_days']
            payslip.jo_unpaid_leave_days = metrics['unpaid_leave_days']
            payslip.jo_loan_installment = metrics['loan_amount']
            payslip.jo_advance_deduction = metrics['advance_amount']
            payslip.jo_overtime_amount = metrics['overtime_amount']

    def _get_jo_input_type(self, code):
        return self.env['hr.payslip.input.type'].search([('code', '=', code)], limit=1)

    def _get_jo_contract(self):
        self.ensure_one()
        contract = self.contract_id
        if not contract and 'version_id' in self._fields:
            contract = self.version_id
        if not contract and self.employee_id:
            employee = self.employee_id.sudo()
            contract = getattr(employee, 'version_id', False) or getattr(employee, 'contract_id', False)
        return contract

    def _get_jo_daily_rate(self):
        self.ensure_one()
        contract = self._get_jo_contract()
        wage = contract.wage if contract else 0.0
        divisor = self.company_id.payroll_daily_wage_divisor or 30
        if divisor <= 0:
            divisor = 30
        return wage / float(divisor) if wage else 0.0

    def _collect_absence_days(self):
        self.ensure_one()
        if not self.company_id.payroll_absence_deduction_enabled:
            return 0.0
        DailyStatus = self.env['hr.attendance.daily.status']
        records = DailyStatus.search([
            ('employee_id', '=', self.employee_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('status', '=', 'absent'),
            ('is_on_approved_leave', '=', False),
            ('is_public_holiday', '=', False),
        ])
        return float(len(records))

    def _collect_unpaid_leave_days(self):
        self.ensure_one()
        leaves = self.env['hr.leave'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'validate'),
            ('holiday_status_id.unpaid', '=', True),
            ('date_from', '<=', fields.Datetime.to_datetime(self.date_to)),
            ('date_to', '>=', fields.Datetime.to_datetime(self.date_from)),
        ])
        total = 0.0
        for leave in leaves:
            total += leave.number_of_days
        return total

    def _collect_overtime_amount(self):
        self.ensure_one()
        requests = self.env['hr.overtime.request'].search([
            ('employee_id', '=', self.employee_id.id),
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'hr_approved'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ])
        return sum(requests.mapped('total_cost'))

    def _collect_loan_installment(self):
        self.ensure_one()
        loans = self.env['hr.employee.loan'].search([
            ('employee_id', '=', self.employee_id.id),
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'hr_approved'),
            ('amount_remaining', '>', 0),
            ('deduction_start_date', '<=', self.date_to),
            ('deduction_end_date', '>=', self.date_from),
        ])
        total = 0.0
        for loan in loans:
            if loan.payment_ids.filtered(lambda payment: payment.payslip_id == self):
                continue
            total += min(loan.monthly_installment, loan.amount_remaining)
        return total

    def _collect_advance_deduction(self):
        self.ensure_one()
        advances = self.env['hr.employee.advance'].search([
            ('employee_id', '=', self.employee_id.id),
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'hr_approved'),
            ('deduct_from_next_payslip', '=', True),
            ('amount_remaining', '>', 0),
        ])
        total = 0.0
        for advance in advances:
            if advance.repayment_ids.filtered(lambda repayment: repayment.payslip_id == self):
                continue
            total += advance.amount_remaining
        return total

    def _collect_jordan_payroll_metrics(self):
        self.ensure_one()
        daily_rate = self._get_jo_daily_rate()
        absence_days = self._collect_absence_days()
        unpaid_days = self._collect_unpaid_leave_days()
        return {
            'absence_days': absence_days,
            'unpaid_leave_days': unpaid_days,
            'absence_amount': absence_days * daily_rate,
            'unpaid_amount': unpaid_days * daily_rate,
            'loan_amount': self._collect_loan_installment(),
            'advance_amount': self._collect_advance_deduction(),
            'overtime_amount': self._collect_overtime_amount(),
        }

    def _upsert_jo_input_line(self, code, amount, label):
        self.ensure_one()
        input_type = self._get_jo_input_type(code)
        if not input_type:
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

    def _sync_jordan_custom_inputs(self):
        for payslip in self:
            if not payslip.employee_id or not payslip.date_from or not payslip.date_to:
                continue
            metrics = payslip._collect_jordan_payroll_metrics()
            payslip._upsert_jo_input_line(
                'OVERTIME',
                metrics['overtime_amount'],
                _('Overtime Allowance'),
            )
            payslip._upsert_jo_input_line(
                'ABSENCE',
                metrics['absence_amount'],
                _('Absence Deduction (%s days)', metrics['absence_days']),
            )
            payslip._upsert_jo_input_line(
                'UNPAID',
                metrics['unpaid_amount'],
                _('Unpaid Leave Deduction (%s days)', metrics['unpaid_leave_days']),
            )
            payslip._upsert_jo_input_line(
                'LOAN',
                metrics['loan_amount'],
                _('Loan Installment'),
            )
            payslip._upsert_jo_input_line(
                'ADVANCE',
                metrics['advance_amount'],
                _('Salary Advance Recovery'),
            )

    def compute_sheet(self):
        self._sync_jordan_custom_inputs()
        return super().compute_sheet()

    def _get_jo_input_amount(self, code):
        self.ensure_one()
        lines = self.input_line_ids.filtered(lambda line: line.input_type_id.code == code)
        return sum(lines.mapped('amount'))

    def _post_jordan_loan_advance_deductions(self):
        for payslip in self:
            if payslip.jo_deductions_posted:
                continue
            loan_amount = payslip._get_jo_input_amount('LOAN')
            if loan_amount > 0:
                payslip._register_loan_payments(loan_amount)
            advance_amount = payslip._get_jo_input_amount('ADVANCE')
            if advance_amount > 0:
                payslip._register_advance_repayments(advance_amount)
            if loan_amount > 0 or advance_amount > 0:
                payslip.jo_deductions_posted = True

    def _register_loan_payments(self, total_amount):
        self.ensure_one()
        remaining = total_amount
        loans = self.env['hr.employee.loan'].search([
            ('employee_id', '=', self.employee_id.id),
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ('hr_approved', 'done')),
            ('amount_remaining', '>', 0),
            ('deduction_start_date', '<=', self.date_to),
            ('deduction_end_date', '>=', self.date_from),
        ], order='deduction_start_date, id')
        for loan in loans:
            if remaining <= 0:
                break
            if loan.payment_ids.filtered(lambda payment: payment.payslip_id == self):
                continue
            installment = min(loan.monthly_installment, loan.amount_remaining, remaining)
            if installment <= 0:
                continue
            payment_count_before = len(loan.payment_ids)
            loan.register_payment(installment, payment_date=self.date_to, source='payslip')
            new_payments = loan.payment_ids.sorted('id')[payment_count_before:]
            for payment in new_payments:
                payment.payslip_id = self.id
            remaining -= installment

    def _register_advance_repayments(self, total_amount):
        self.ensure_one()
        remaining = total_amount
        advances = self.env['hr.employee.advance'].search([
            ('employee_id', '=', self.employee_id.id),
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ('hr_approved', 'repaid')),
            ('deduct_from_next_payslip', '=', True),
            ('amount_remaining', '>', 0),
        ], order='request_date, id')
        for advance in advances:
            if remaining <= 0:
                break
            if advance.repayment_ids.filtered(lambda repayment: repayment.payslip_id == self):
                continue
            repayment_amount = min(advance.amount_remaining, remaining)
            if repayment_amount <= 0:
                continue
            repayment_count_before = len(advance.repayment_ids)
            advance.register_repayment(repayment_amount, repayment_date=self.date_to, source='payslip')
            new_repayments = advance.repayment_ids.sorted('id')[repayment_count_before:]
            for repayment in new_repayments:
                repayment.payslip_id = self.id
            remaining -= repayment_amount

    def _reverse_jordan_loan_advance_deductions(self):
        for payslip in self:
            if not payslip.jo_deductions_posted:
                continue
            for payment in payslip.env['hr.employee.loan.payment'].search([
                ('payslip_id', '=', payslip.id),
            ]):
                loan = payment.loan_id
                loan.amount_paid = max(loan.amount_paid - payment.amount, 0.0)
                if loan.state == 'done' and loan.amount_remaining > 0:
                    loan.state = 'hr_approved'
                payment.unlink()
            for repayment in payslip.env['hr.employee.advance.repayment'].search([
                ('payslip_id', '=', payslip.id),
            ]):
                advance = repayment.advance_id
                advance.amount_repaid = max(advance.amount_repaid - repayment.amount, 0.0)
                if advance.state == 'repaid' and advance.amount_remaining > 0:
                    advance.state = 'hr_approved'
                repayment.unlink()
            payslip.jo_deductions_posted = False

    def action_payslip_done(self):
        self._post_jordan_loan_advance_deductions()
        return super().action_payslip_done()

    def refund_sheet(self):
        self._reverse_jordan_loan_advance_deductions()
        return super().refund_sheet()

    def action_payslip_cancel(self):
        self._reverse_jordan_loan_advance_deductions()
        return super().action_payslip_cancel()

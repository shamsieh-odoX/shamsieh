# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class HrEmployeeLoan(models.Model):
    _name = 'hr.employee.loan'
    _description = 'Employee Loan'
    _inherit = 'hr.loans.advances.approval.mixin'
    _order = 'deduction_start_date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    total_amount = fields.Monetary(
        string='Total Loan Amount',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    monthly_installment = fields.Monetary(
        string='Monthly Installment',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    deduction_start_date = fields.Date(
        string='Deduction Start Date',
        required=True,
        tracking=True,
    )
    deduction_end_date = fields.Date(
        string='Deduction End Date',
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('manager_approved', 'Manager Approved'),
            ('upper_manager_approved', 'Upper Manager Approved'),
            ('hr_approved', 'Active'),
            ('done', 'Paid Off'),
            ('refused', 'Refused'),
            ('cancel', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    amount_paid = fields.Monetary(
        string='Amount Paid',
        currency_field='currency_id',
        readonly=True,
        copy=False,
    )
    amount_remaining = fields.Monetary(
        string='Amount Remaining',
        compute='_compute_amount_remaining',
        store=True,
        currency_field='currency_id',
    )
    approval_line_ids = fields.One2many(
        'hr.employee.loan.approval.line',
        'request_id',
        string='Approval History',
        copy=False,
    )
    payment_ids = fields.One2many(
        'hr.employee.loan.payment',
        'loan_id',
        string='Payments',
        copy=False,
    )
    payment_count = fields.Integer(compute='_compute_payment_count')

    @api.depends('total_amount', 'amount_paid')
    def _compute_amount_remaining(self):
        for loan in self:
            loan.amount_remaining = max(loan.total_amount - loan.amount_paid, 0.0)

    @api.depends('payment_ids')
    def _compute_payment_count(self):
        for loan in self:
            loan.payment_count = len(loan.payment_ids)

    @api.constrains('total_amount', 'monthly_installment', 'deduction_start_date', 'deduction_end_date')
    def _check_loan_values(self):
        for loan in self:
            if loan.total_amount <= 0:
                raise ValidationError(_('Total loan amount must be greater than zero.'))
            if loan.monthly_installment <= 0:
                raise ValidationError(_('Monthly installment must be greater than zero.'))
            if loan.monthly_installment > loan.total_amount:
                raise ValidationError(_('Monthly installment cannot exceed the total loan amount.'))
            if loan.deduction_start_date and loan.deduction_end_date:
                if loan.deduction_end_date < loan.deduction_start_date:
                    raise ValidationError(_('Deduction end date must be on or after the start date.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.employee.loan') or _('New')
        return super(HrEmployeeLoan, self._loans_advances_env()).create(vals_list)

    @api.model
    def action_open_my_loans(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'hr_loans_advances.action_hr_employee_loan',
        )
        return self._merge_action_context(action, {'search_default_my_loans': 1})

    def _protected_write_fields(self):
        return {
            'employee_id', 'company_id', 'total_amount', 'monthly_installment',
            'deduction_start_date', 'deduction_end_date',
        }

    def _approval_line_model(self):
        return 'hr.employee.loan.approval.line'

    def _approval_line_inverse_field(self):
        return 'request_id'

    def _build_manager_hr_approval_chain(self, employee):
        """Three-step loan chain: manager → upper manager → HR."""
        service = self._get_approval_chain_service()
        return service.build_manager_hr_chain(
            employee.sudo(),
            hr_group_xmlid=self._approval_hr_group_xmlid(),
        )

    def _on_approval_complete(self):
        for loan in self:
            loan.sudo().message_post(body=_('Employee loan approved and is now active for deductions.'))

    def action_submit(self):
        for record in self:
            record._submit_for_approval()
        return True

    def action_open_refuse_wizard(self):
        self.ensure_one()
        line = self.sudo()._get_active_approval_line()
        if not line:
            raise UserError(_('No pending approval step found.'))
        if not self._can_user_approve_line(line):
            from odoo.exceptions import AccessError
            raise AccessError(_('You are not allowed to refuse this request.'))
        return {
            'name': _('Refuse Loan'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.loan.refuse.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_loan_id': self.id,
                'default_approval_line_id': line.id,
            },
        }

    def _has_monthly_payment_for(self, as_of_date):
        self.ensure_one()
        month_start = date(as_of_date.year, as_of_date.month, 1)
        if as_of_date.month == 12:
            month_end = date(as_of_date.year + 1, 1, 1)
        else:
            month_end = date(as_of_date.year, as_of_date.month + 1, 1)
        return bool(self.payment_ids.filtered(
            lambda payment: payment.source == 'monthly'
            and month_start <= payment.date < month_end
        ))

    def register_payment(self, amount, payment_date=None, source='manual'):
        self.ensure_one()
        if self.state not in ('hr_approved', 'done'):
            raise UserError(_('Payments can only be registered on active loans.'))
        if amount <= 0:
            raise UserError(_('Payment amount must be greater than zero.'))
        if amount > self.amount_remaining:
            raise UserError(_(
                'Payment amount (%(amount).2f) exceeds the remaining balance (%(remaining).2f).',
                amount=amount,
                remaining=self.amount_remaining,
            ))
        payment_date = payment_date or fields.Date.context_today(self)
        new_paid = self.amount_paid + amount
        balance_after = max(self.total_amount - new_paid, 0.0)
        self.env['hr.employee.loan.payment'].create({
            'loan_id': self.id,
            'date': payment_date,
            'amount': amount,
            'source': source,
            'balance_after': balance_after,
        })
        vals = {'amount_paid': new_paid}
        if balance_after <= 0:
            vals['state'] = 'done'
        self.write(vals)
        return True

    def apply_monthly_deduction(self, as_of_date=None):
        self.ensure_one()
        as_of_date = as_of_date or fields.Date.context_today(self)
        if self.state != 'hr_approved' or self.amount_remaining <= 0:
            return False
        if as_of_date < self.deduction_start_date or as_of_date > self.deduction_end_date:
            return False
        if self._has_monthly_payment_for(as_of_date):
            return False
        amount = min(self.monthly_installment, self.amount_remaining)
        if amount <= 0:
            return False
        self.register_payment(amount, payment_date=as_of_date, source='monthly')
        return True

    @api.model
    def action_apply_monthly_deductions(self, as_of_date=None):
        as_of_date = as_of_date or fields.Date.context_today(self)
        loans = self.search([
            ('state', '=', 'hr_approved'),
            ('amount_remaining', '>', 0),
            ('deduction_start_date', '<=', as_of_date),
            ('deduction_end_date', '>=', as_of_date),
        ])
        applied = self.env['hr.employee.loan']
        for loan in loans:
            if loan.apply_monthly_deduction(as_of_date):
                applied += loan
        return applied

    def action_view_payments(self):
        self.ensure_one()
        return {
            'name': _('Loan Payments'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee.loan.payment',
            'view_mode': 'list,form',
            'domain': [('loan_id', '=', self.id)],
            'context': {'default_loan_id': self.id},
        }

    def action_view_approval_lines(self):
        self.ensure_one()
        return {
            'name': _('Approval History'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee.loan.approval.line',
            'view_mode': 'list,form',
            'domain': [('request_id', '=', self.id)],
            'context': {'default_request_id': self.id},
        }

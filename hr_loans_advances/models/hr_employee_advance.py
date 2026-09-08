# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class HrEmployeeAdvance(models.Model):
    _name = 'hr.employee.advance'
    _description = 'Employee Salary Advance'
    _inherit = 'hr.loans.advances.approval.mixin'
    _order = 'request_date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    request_date = fields.Date(
        string='Request Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    amount = fields.Monetary(
        string='Amount',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    reason = fields.Text(string='Reason', tracking=True)
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('manager_approved', 'Manager Approved'),
            ('hr_approved', 'Approved'),
            ('repaid', 'Repaid'),
            ('refused', 'Refused'),
            ('cancel', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    amount_repaid = fields.Monetary(
        string='Amount Repaid',
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
    deduct_from_next_payslip = fields.Boolean(
        string='Deduct from Next Payslip',
        default=True,
        help='Reserved for future payroll integration.',
    )
    approval_line_ids = fields.One2many(
        'hr.employee.advance.approval.line',
        'request_id',
        string='Approval History',
        copy=False,
    )
    repayment_ids = fields.One2many(
        'hr.employee.advance.repayment',
        'advance_id',
        string='Repayments',
        copy=False,
    )

    @api.depends('amount', 'amount_repaid')
    def _compute_amount_remaining(self):
        for advance in self:
            advance.amount_remaining = max(advance.amount - advance.amount_repaid, 0.0)

    @api.constrains('amount')
    def _check_amount_positive(self):
        for advance in self:
            if advance.amount <= 0:
                raise ValidationError(_('Advance amount must be greater than zero.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.employee.advance') or _('New')
        return super(HrEmployeeAdvance, self._loans_advances_env()).create(vals_list)

    @api.model
    def action_open_my_advances(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'hr_loans_advances.action_hr_employee_advance',
        )
        return self._merge_action_context(action, {'search_default_my_advances': 1})

    def _protected_write_fields(self):
        return {'employee_id', 'company_id', 'request_date', 'amount', 'reason', 'deduct_from_next_payslip'}

    def _approval_line_model(self):
        return 'hr.employee.advance.approval.line'

    def _approval_line_inverse_field(self):
        return 'request_id'

    def _on_approval_complete(self):
        for advance in self:
            advance.sudo().message_post(body=_('Salary advance approved.'))

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
            'name': _('Refuse Advance'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.advance.refuse.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_advance_id': self.id,
                'default_approval_line_id': line.id,
            },
        }

    def register_repayment(self, amount, repayment_date=None, source='manual'):
        self.ensure_one()
        if self.state not in ('hr_approved', 'repaid'):
            raise UserError(_('Repayments can only be registered on approved advances.'))
        if amount <= 0:
            raise UserError(_('Repayment amount must be greater than zero.'))
        if amount > self.amount_remaining:
            raise UserError(_(
                'Repayment amount (%(amount).2f) exceeds the remaining balance (%(remaining).2f).',
                amount=amount,
                remaining=self.amount_remaining,
            ))
        repayment_date = repayment_date or fields.Date.context_today(self)
        new_repaid = self.amount_repaid + amount
        balance_after = max(self.amount - new_repaid, 0.0)
        self.env['hr.employee.advance.repayment'].create({
            'advance_id': self.id,
            'date': repayment_date,
            'amount': amount,
            'source': source,
            'balance_after': balance_after,
        })
        vals = {'amount_repaid': new_repaid}
        if balance_after <= 0:
            vals['state'] = 'repaid'
        self.write(vals)
        return True

    def action_view_approval_lines(self):
        self.ensure_one()
        return {
            'name': _('Approval History'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee.advance.approval.line',
            'view_mode': 'list,form',
            'domain': [('request_id', '=', self.id)],
            'context': {'default_request_id': self.id},
        }

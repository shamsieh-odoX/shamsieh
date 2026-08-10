# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrEmployeeLoanPayment(models.Model):
    _name = 'hr.employee.loan.payment'
    _description = 'Loan Payment'
    _order = 'date desc, id desc'

    loan_id = fields.Many2one(
        'hr.employee.loan',
        string='Loan',
        required=True,
        ondelete='cascade',
        index=True,
    )
    currency_id = fields.Many2one(
        related='loan_id.currency_id',
        store=True,
        readonly=True,
    )
    date = fields.Date(string='Payment Date', required=True, default=fields.Date.context_today)
    amount = fields.Monetary(string='Amount', required=True, currency_field='currency_id')
    source = fields.Selection(
        selection=[
            ('manual', 'Manual'),
            ('monthly', 'Monthly Deduction'),
            ('payslip', 'Payslip'),
        ],
        string='Source',
        required=True,
        default='manual',
    )
    balance_after = fields.Monetary(
        string='Balance After',
        currency_field='currency_id',
        readonly=True,
    )

# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrEmployeeAdvanceRepayment(models.Model):
    _name = 'hr.employee.advance.repayment'
    _description = 'Advance Repayment'
    _order = 'date desc, id desc'

    advance_id = fields.Many2one(
        'hr.employee.advance',
        string='Advance',
        required=True,
        ondelete='cascade',
        index=True,
    )
    currency_id = fields.Many2one(
        related='advance_id.currency_id',
        store=True,
        readonly=True,
    )
    date = fields.Date(string='Repayment Date', required=True, default=fields.Date.context_today)
    amount = fields.Monetary(string='Amount', required=True, currency_field='currency_id')
    source = fields.Selection(
        selection=[
            ('manual', 'Manual'),
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

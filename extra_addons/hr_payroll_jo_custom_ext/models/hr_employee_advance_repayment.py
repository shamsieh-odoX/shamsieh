# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrEmployeeAdvanceRepayment(models.Model):
    _inherit = 'hr.employee.advance.repayment'

    payslip_id = fields.Many2one(
        'hr.payslip',
        string='Payslip',
        ondelete='set null',
        index=True,
        copy=False,
    )

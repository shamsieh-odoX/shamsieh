# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrPayslipBreakdownReportWizard(models.TransientModel):
    _name = 'hr.payslip.breakdown.report.wizard'
    _description = 'Payslip Breakdown Report Wizard'

    date_from = fields.Date(string='From', required=True)
    date_to = fields.Date(string='To', required=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    department_id = fields.Many2one('hr.department', string='Department')
    employee_ids = fields.Many2many('hr.employee', string='Employees')
    payslip_state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('verify', 'Waiting'),
            ('done', 'Done'),
            ('cancel', 'Cancelled'),
        ],
        string='Payslip Status',
        default='done',
        required=True,
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise UserError(_('The start date must be before the end date.'))

    def action_print_report(self):
        self.ensure_one()
        data = {
            'form': {
                'date_from': fields.Date.to_string(self.date_from),
                'date_to': fields.Date.to_string(self.date_to),
                'company_id': self.company_id.id,
                'department_id': self.department_id.id if self.department_id else False,
                'employee_ids': self.employee_ids.ids,
                'payslip_state': self.payslip_state,
            },
        }
        return self.env.ref(
            'hr_payroll_custom_ext.action_report_payslip_breakdown'
        ).report_action(self, data=data)

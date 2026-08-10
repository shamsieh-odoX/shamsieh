# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    overtime_request_count = fields.Integer(compute='_compute_overtime_request_count')
    overtime_hours_ytd = fields.Float(
        string='Overtime Hours (YTD)',
        compute='_compute_overtime_stats',
    )
    overtime_cost_ytd = fields.Monetary(
        string='Overtime Cost (YTD)',
        compute='_compute_overtime_stats',
        currency_field='company_currency_id',
    )
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Company Currency',
    )

    def _compute_overtime_request_count(self):
        request_data = self.env['hr.overtime.request']._read_group(
            [('employee_id', 'in', self.ids), ('state', '=', 'hr_approved')],
            ['employee_id'],
            ['__count'],
        )
        counts = {employee.id: count for employee, count in request_data}
        for employee in self:
            employee.overtime_request_count = counts.get(employee.id, 0)

    def _compute_overtime_stats(self):
        year_start = fields.Date.today().replace(month=1, day=1)
        request_data = self.env['hr.overtime.request']._read_group(
            [
                ('employee_id', 'in', self.ids),
                ('state', '=', 'hr_approved'),
                ('date', '>=', year_start),
            ],
            ['employee_id'],
            ['overtime_hours:sum', 'total_cost:sum'],
        )
        stats = {
            employee.id: (hours, cost)
            for employee, hours, cost in request_data
        }
        for employee in self:
            hours, cost = stats.get(employee.id, (0.0, 0.0))
            employee.overtime_hours_ytd = hours
            employee.overtime_cost_ytd = cost

    def action_view_overtime_requests(self):
        self.ensure_one()
        return {
            'name': self.env._('Overtime Requests'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.overtime.request',
            'view_mode': 'list,form,kanban,pivot,graph',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

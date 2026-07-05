# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models


class HrOvertimeRequest(models.Model):
    _inherit = 'hr.overtime.request'

    payslip_input_id = fields.Many2one(
        'hr.payslip.input',
        string='Payslip Input',
        copy=False,
        readonly=True,
    )

    def _get_hourly_cost_value(self):
        self.ensure_one()
        if not self.company_id.overtime_link_to_payroll:
            return super()._get_hourly_cost_value()
        employee = self.employee_id.sudo()
        version = employee.version_id
        if not version:
            return super()._get_hourly_cost_value()
        hourly = version._get_normalized_wage()
        if hourly:
            return hourly
        wage = version.wage or getattr(version, 'contract_wage', 0.0)
        if not wage:
            return 0.0
        hours_per_month = self.company_id.overtime_hours_per_month or 173.33
        return wage / hours_per_month

    def _on_approval_complete(self):
        super()._on_approval_complete()
        for request in self:
            if request.company_id.overtime_link_to_payroll:
                request._create_or_update_payslip_input()

    def _create_or_update_payslip_input(self):
        self.ensure_one()
        input_type = self.env.ref(
            'hr_overtime_payroll.payslip_input_type_overtime',
            raise_if_not_found=False,
        )
        if not input_type:
            return
        version = self.employee_id.sudo().version_id
        if not version:
            return
        payslip = self._find_open_payslip()
        if not payslip:
            return
        existing = payslip.input_line_ids.filtered(
            lambda line: line.input_type_id == input_type
            and line.name == self.name
        )
        employee = self.employee_id.sudo()
        vals = {
            'name': self.name,
            'amount': self.total_cost,
            'input_type_id': input_type.id,
        }
        payslip_input_model = self.env['hr.payslip.input']
        if 'contract_id' in payslip_input_model._fields:
            contract = getattr(employee, 'contract_id', False)
            if contract:
                vals['contract_id'] = contract.id
        if existing:
            existing.write(vals)
            self.payslip_input_id = existing[0]
        else:
            input_line = self.env['hr.payslip.input'].create({
                **vals,
                'payslip_id': payslip.id,
            })
            self.payslip_input_id = input_line

    def _find_open_payslip(self):
        self.ensure_one()
        return self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id.id),
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ('draft', 'verify')),
            ('date_from', '<=', self.date),
            ('date_to', '>=', self.date),
        ], limit=1, order='date_from desc')

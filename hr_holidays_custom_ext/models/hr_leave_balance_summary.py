# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date

from odoo import api, fields, models


class HrLeaveBalanceSummary(models.Model):
    _name = 'hr.leave.balance.summary'
    _description = 'Employee Leave Balance Summary'
    _order = 'employee_id, leave_type_id'

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, index=True)
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True,
        readonly=True,
    )
    leave_type_id = fields.Many2one('hr.leave.type', string='Time Off Type', required=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, index=True)
    as_of_date = fields.Date(string='As Of Date', required=True, index=True)
    total_accrued = fields.Float(string='Total Accrued', digits=(16, 2))
    days_used = fields.Float(string='Days Used', digits=(16, 2))
    days_remaining = fields.Float(string='Days Remaining', digits=(16, 2))
    carried_over = fields.Float(string='Carried-Over Balance', digits=(16, 2))
    current_year_balance = fields.Float(string='Current-Year Balance', digits=(16, 2))
    total_available = fields.Float(string='Total Available', digits=(16, 2))

    @api.model
    def _default_as_of_date(self):
        return fields.Date.context_today(self)

    @api.model
    def _get_balance_row(self, employee, leave_type, as_of_date):
        if isinstance(as_of_date, str):
            as_of_date = fields.Date.from_string(as_of_date)

        allocation_data = leave_type.get_allocation_data(employee, as_of_date).get(employee, [])
        info = next(
            (item[1] for item in allocation_data if len(item) > 3 and item[3] == leave_type.id),
            None,
        )
        if not info:
            return None

        allocations = self.env['hr.leave.allocation'].sudo().search([
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', leave_type.id),
            ('state', '=', 'validate'),
            ('date_from', '<=', as_of_date),
            '|', ('date_to', '=', False), ('date_to', '>=', as_of_date),
        ])
        carried_over = sum(allocations.mapped('expiring_carryover_days'))
        year_start = date(as_of_date.year, 1, 1)
        year_leaves = self.env['hr.leave'].sudo().search([
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', leave_type.id),
            ('state', '=', 'validate'),
            ('date_from', '>=', fields.Datetime.to_datetime(year_start)),
            ('date_from', '<=', fields.Datetime.to_datetime(as_of_date)),
        ])
        taken_this_year = sum(year_leaves.mapped('number_of_days'))
        accrued_this_year = max(0.0, info['max_leaves'] - carried_over)
        current_year_balance = max(0.0, accrued_this_year - taken_this_year)
        return {
            'employee_id': employee.id,
            'leave_type_id': leave_type.id,
            'company_id': employee.company_id.id,
            'as_of_date': as_of_date,
            'total_accrued': info.get('max_leaves', 0.0),
            'days_used': info.get('leaves_taken', 0.0),
            'days_remaining': info.get('remaining_leaves', 0.0),
            'carried_over': carried_over,
            'current_year_balance': current_year_balance,
            'total_available': info.get('virtual_remaining_leaves', 0.0),
        }

    @api.model
    def _collect_balance_rows(self, as_of_date=None, company_id=None, department_id=None, leave_type_id=None):
        as_of_date = as_of_date or self._default_as_of_date()
        if isinstance(as_of_date, str):
            as_of_date = fields.Date.from_string(as_of_date)

        employee_domain = [('active', '=', True)]
        if company_id:
            employee_domain.append(('company_id', '=', company_id))
        if department_id:
            employee_domain.append(('department_id', '=', department_id))
        employees = self.env['hr.employee'].search(employee_domain)

        leave_type_domain = [('requires_allocation', '=', True)]
        if company_id:
            leave_type_domain += [
                '|', ('company_id', '=', False), ('company_id', '=', company_id),
            ]
        if leave_type_id:
            leave_type_domain.append(('id', '=', leave_type_id))
        leave_types = self.env['hr.leave.type'].search(leave_type_domain)

        rows = []
        for employee in employees:
            for leave_type in leave_types:
                row = self._get_balance_row(employee, leave_type, as_of_date)
                if row:
                    rows.append(row)
        return rows

    @api.model
    def rebuild_summary(self, as_of_date=None, company_id=None, department_id=None, leave_type_id=None):
        as_of_date = as_of_date or self._default_as_of_date()
        domain = [('as_of_date', '=', as_of_date)]
        if company_id:
            domain.append(('company_id', '=', company_id))
        if department_id:
            domain.append(('department_id', '=', department_id))
        if leave_type_id:
            domain.append(('leave_type_id', '=', leave_type_id))
        self.search(domain).unlink()
        rows = self._collect_balance_rows(
            as_of_date=as_of_date,
            company_id=company_id,
            department_id=department_id,
            leave_type_id=leave_type_id,
        )
        if rows:
            return self.create(rows)
        return self.browse()

    @api.model
    def action_open_report(self):
        as_of_date = self.env.context.get('default_as_of_date') or self._default_as_of_date()
        company_id = self.env.context.get('default_company_id') or self.env.company.id
        self.rebuild_summary(as_of_date=as_of_date, company_id=company_id)
        return {
            'name': 'Employee Balance Summary',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.leave.balance.summary',
            'view_mode': 'list',
            'domain': [
                ('as_of_date', '=', as_of_date),
                ('company_id', '=', company_id),
            ],
            'context': {
                'default_as_of_date': as_of_date,
                'default_company_id': company_id,
            },
        }

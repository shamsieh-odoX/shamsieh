# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class HrHourlyDepartureBalance(models.Model):
    _name = 'hr.hourly.departure.balance'
    _description = 'Hourly Departure Accumulated Hours'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one(
        'hr.employee',
        required=True,
        index=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        'res.company',
        related='employee_id.company_id',
        store=True,
        index=True,
    )
    accumulated_hours = fields.Float(
        string='Accumulated Hours',
        default=0.0,
        help='Remainder of validated departure hours not yet converted to annual leave.',
    )

    _sql_constraints = [
        (
            'employee_uniq',
            'unique(employee_id)',
            'Each employee can only have one hourly departure balance.',
        ),
    ]

    @api.model
    def _get_or_create_for_employee(self, employee):
        balance = self.sudo().search([('employee_id', '=', employee.id)], limit=1)
        if balance:
            return balance
        return self.sudo().create({
            'employee_id': employee.id,
            'accumulated_hours': 0.0,
        })

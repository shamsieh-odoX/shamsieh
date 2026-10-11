# -*- coding: utf-8 -*-
from odoo import fields, models

# Presence widgets load these via fieldDependencies; own-data users must be able to read them.
_OWN = 'hr.group_hr_user,hr_employee_own_data.group_hr_own_data'


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    current_leave_id = fields.Many2one(groups=_OWN)
    current_leave_state = fields.Selection(
        selection=[
            ('confirm', 'Waiting Approval'),
            ('refuse', 'Refused'),
            ('validate1', 'Waiting Second Approval'),
            ('validate', 'Approved'),
            ('cancel', 'Cancelled'),
        ],
        groups=_OWN,
    )
    leave_date_from = fields.Date(groups=_OWN)
    allocation_count = fields.Float(groups=_OWN)
    allocations_count = fields.Integer(groups=_OWN)

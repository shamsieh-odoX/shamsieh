# -*- coding: utf-8 -*-
from odoo import fields, models

_OWN = 'hr.group_hr_user,hr_employee_own_data.group_hr_own_data'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Needed when the employee form loads work contacts / manager cards.
    employee_ids = fields.One2many(groups=_OWN)
    employees_count = fields.Integer(groups=_OWN)

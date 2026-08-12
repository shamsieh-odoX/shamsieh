# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    # Expose live attendance status in the public employee profile context
    # to avoid read errors when non-HR users open records that reference it.
    hikvision_presence_status = fields.Selection(
        related='employee_id.hikvision_presence_status',
        readonly=True,
    )

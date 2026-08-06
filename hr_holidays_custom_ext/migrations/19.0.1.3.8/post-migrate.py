# -*- coding: utf-8 -*-
"""Ensure Paid Time Off requires manager then officer/GM approval.

Do not use SQL ILIKE on ``hr_leave_type.name`` — it is a translated
JSON field in Odoo 19 and breaks upgrades with:
  operator does not exist: jsonb ~~* unknown
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    LeaveType = env['hr.leave.type'].sudo()
    leave_types = LeaveType.search([
        ('requires_allocation', '=', True),
        '|', '|', '|',
        ('name', 'ilike', 'paid time off'),
        ('name', 'ilike', 'legal leave'),
        ('name', 'ilike', 'annual'),
        ('name', 'ilike', 'pto'),
    ])
    if leave_types:
        leave_types.write({'leave_validation_type': 'both'})
        _logger.info(
            'hr_holidays_custom_ext: set leave_validation_type=both on %s',
            leave_types.mapped('name'),
        )

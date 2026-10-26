# -*- coding: utf-8 -*-
"""Point Notify HR (second approval display) at Mohaned for two-step leave types."""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    mohaned = env['res.users'].sudo().search([
        '|',
        ('login', '=', 'mohaned@shamsieh.com'),
        ('name', 'ilike', 'Mohaned'),
    ], limit=1)
    if not mohaned:
        _logger.warning(
            'hr_holidays_custom_ext 19.0.1.5.6: Mohaned user not found; skip Notify HR update'
        )
        return
    leave_types = env['hr.leave.type'].sudo().search([
        ('leave_validation_type', '=', 'both'),
    ])
    if leave_types:
        leave_types.write({'responsible_ids': [(6, 0, [mohaned.id])]})
        _logger.info(
            'hr_holidays_custom_ext: set Notify HR=%s on %s two-step leave type(s)',
            mohaned.login,
            len(leave_types),
        )

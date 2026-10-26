# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Force two-step validation on leave types so confirm → validate1 → validate works.

    Types with ``no_validation`` are left unchanged.
    """
    leave_types = env['hr.leave.type'].sudo().search([
        ('leave_validation_type', '!=', 'no_validation'),
    ])
    if leave_types:
        leave_types.write({'leave_validation_type': 'both'})
        _logger.info(
            'hr_holidays_custom_approval: set leave_validation_type=both on %s type(s)',
            len(leave_types),
        )

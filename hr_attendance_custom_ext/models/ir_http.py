# -*- coding: utf-8 -*-

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @api.model
    def lazy_session_info(self):
        res = super().lazy_session_info()
        employee = self.env.user.employee_id
        if not employee:
            return res
        try:
            res['attendance_user_data'] = employee._get_attendance_systray_user_data()
        except Exception:
            # Keep the backend usable if DB schema is behind code (module not upgraded yet).
            _logger.exception(
                'Failed to load attendance systray data for employee %s',
                employee.id,
            )
        return res

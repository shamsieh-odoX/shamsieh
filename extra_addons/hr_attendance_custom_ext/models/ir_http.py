# -*- coding: utf-8 -*-

from odoo import api, models

from odoo.addons.hr_attendance_custom_ext.controllers.hr_attendance import HrAttendanceCustom


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @api.model
    def lazy_session_info(self):
        res = super().lazy_session_info()
        if self.env.user and self.env.user.employee_id:
            employee = self.env.user.employee_id
            res['attendance_user_data'] = HrAttendanceCustom._get_user_attendance_data(employee)
        return res

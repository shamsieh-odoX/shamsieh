# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError


class HrExceptionalHolidayRefuseWizard(models.TransientModel):
    _name = 'hr.exceptional.holiday.refuse.wizard'
    _description = 'Refuse Exceptional Holiday Request'

    holiday_request_id = fields.Many2one(
        'hr.exceptional.holiday',
        string='Exceptional Holiday',
        required=True,
    )
    approval_line_id = fields.Many2one(
        'hr.exceptional.holiday.approval.line',
        string='Approval Step',
        required=True,
    )
    reason = fields.Text(string='Reason', required=True)

    def action_refuse(self):
        self.ensure_one()
        if not self.reason.strip():
            raise UserError(_('A refusal reason is required.'))
        request = self.holiday_request_id.sudo()
        line = self.approval_line_id.sudo()
        if line.request_id != request:
            raise UserError(_('The selected approval step does not belong to this request.'))
        if not request._can_user_approve_line(line):
            raise AccessError(_('You are not allowed to refuse this request.'))
        request.action_process_refusal(line, self.reason.strip())
        return {'type': 'ir.actions.act_window_close'}

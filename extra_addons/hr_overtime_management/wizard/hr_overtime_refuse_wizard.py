# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.exceptions import UserError


class HrOvertimeRefuseWizard(models.TransientModel):
    _name = 'hr.overtime.refuse.wizard'
    _description = 'Refuse Overtime Request'

    overtime_request_id = fields.Many2one(
        'hr.overtime.request',
        string='Overtime Request',
        required=True,
    )
    approval_line_id = fields.Many2one(
        'hr.overtime.approval.line',
        string='Approval Step',
        required=True,
    )
    reason = fields.Text(string='Reason', required=True)

    def action_refuse(self):
        self.ensure_one()
        if not self.reason.strip():
            raise UserError(_('A refusal reason is required.'))
        request = self.overtime_request_id
        line = self.approval_line_id
        if line.request_id != request:
            raise UserError(_('The selected approval step does not belong to this request.'))
        request.action_process_refusal(line, self.reason.strip())
        return {'type': 'ir.actions.act_window_close'}

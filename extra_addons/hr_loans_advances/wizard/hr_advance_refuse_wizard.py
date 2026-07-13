# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError


class HrAdvanceRefuseWizard(models.TransientModel):
    _name = 'hr.advance.refuse.wizard'
    _description = 'Refuse Salary Advance'

    advance_id = fields.Many2one(
        'hr.employee.advance',
        string='Advance',
        required=True,
    )
    approval_line_id = fields.Many2one(
        'hr.employee.advance.approval.line',
        string='Approval Step',
        required=True,
    )
    reason = fields.Text(string='Reason', required=True)

    def action_refuse(self):
        self.ensure_one()
        if not self.reason.strip():
            raise UserError(_('A refusal reason is required.'))
        advance = self.advance_id.sudo()
        line = self.approval_line_id.sudo()
        if line.request_id != advance:
            raise UserError(_('The selected approval step does not belong to this advance.'))
        if not advance._can_user_approve_line(line):
            raise AccessError(_('You are not allowed to refuse this request.'))
        advance.action_process_refusal(line, self.reason.strip())
        return {'type': 'ir.actions.act_window_close'}

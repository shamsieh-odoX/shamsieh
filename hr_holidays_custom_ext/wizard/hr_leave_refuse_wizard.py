# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.exceptions import UserError


class HrLeaveRefuseWizard(models.TransientModel):
    _name = 'hr.leave.refuse.wizard'
    _description = 'Refuse Time Off Request'

    leave_id = fields.Many2one(
        'hr.leave',
        string='Time Off Request',
        required=True,
    )
    reason = fields.Text(string='Reason', required=True)

    def action_refuse(self):
        self.ensure_one()
        if not self.reason.strip():
            raise UserError(_('A refusal reason is required.'))
        leave = self.leave_id.sudo()
        leave.action_process_refusal(self.reason.strip())
        return {'type': 'ir.actions.act_window_close'}

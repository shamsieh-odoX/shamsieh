# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class HrRemoteWorkRefuseWizard(models.TransientModel):
    _name = 'hr.remote.work.refuse.wizard'
    _description = 'Refuse Remote Work Request'

    request_id = fields.Many2one(
        'hr.remote.work.request',
        string='Remote Work Request',
        required=True,
    )
    reason = fields.Text(string='Reason', required=True)

    def action_refuse(self):
        self.ensure_one()
        if not self.reason.strip():
            raise UserError(_('A refusal reason is required.'))
        request = self.request_id.sudo()
        request.action_process_refusal(self.reason.strip())
        return {'type': 'ir.actions.act_window_close'}

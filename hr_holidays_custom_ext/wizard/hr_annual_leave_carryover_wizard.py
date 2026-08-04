# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrAnnualLeaveCarryoverWizard(models.TransientModel):
    _name = 'hr.annual.leave.carryover.wizard'
    _description = 'Run Annual Leave Carryover'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    target_year = fields.Integer(
        string='Target Year',
        required=True,
        default=lambda self: fields.Date.today().year,
        help='Calendar year to create annual grants and carryover allocations for.',
    )

    @api.constrains('target_year')
    def _check_target_year(self):
        for wizard in self:
            if wizard.target_year < 2000 or wizard.target_year > 2100:
                raise UserError(_('Target year must be between 2000 and 2100.'))

    def action_run_carryover(self):
        self.ensure_one()
        logs = self.env['hr.annual.leave.carryover.log']._run_carryover(
            company=self.company_id,
            target_year=self.target_year,
            trigger='manual',
            force=True,
        )
        if not logs:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Annual Leave Carryover'),
                    'message': _('No allocations were created or updated.'),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        log = logs[0]
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Annual Leave Carryover Complete'),
                'message': log.summary,
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'hr.annual.leave.carryover.log',
                    'view_mode': 'list,form',
                    'domain': [('id', 'in', logs.ids)],
                    'target': 'current',
                },
            },
        }

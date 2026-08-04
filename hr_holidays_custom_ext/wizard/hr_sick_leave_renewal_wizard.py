# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrSickLeaveRenewalWizard(models.TransientModel):
    _name = 'hr.sick.leave.renewal.wizard'
    _description = 'Run Sick Leave Renewal'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    renewal_year = fields.Integer(
        string='Renewal Year',
        required=True,
        default=lambda self: fields.Date.today().year,
    )

    @api.constrains('renewal_year')
    def _check_renewal_year(self):
        for wizard in self:
            if wizard.renewal_year < 2000 or wizard.renewal_year > 2100:
                raise UserError(_('Renewal year must be between 2000 and 2100.'))

    def action_run_renewal(self):
        self.ensure_one()
        logs = self.env['hr.sick.leave.renewal.log']._run_renewal(
            company=self.company_id,
            year=self.renewal_year,
            trigger='manual',
            force=True,
        )
        if not logs:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sick Leave Renewal'),
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
                'title': _('Sick Leave Renewal Complete'),
                'message': log.summary,
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'hr.sick.leave.renewal.log',
                    'view_mode': 'list,form',
                    'domain': [('id', 'in', logs.ids)],
                    'target': 'current',
                },
            },
        }

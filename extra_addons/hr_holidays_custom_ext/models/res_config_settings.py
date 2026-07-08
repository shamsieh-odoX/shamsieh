# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sick_leave_days_per_year = fields.Integer(
        related='company_id.sick_leave_days_per_year',
        readonly=False,
    )
    sick_leave_last_renewal_date = fields.Datetime(
        string='Last Sick Leave Renewal',
        compute='_compute_sick_leave_last_renewal',
    )
    sick_leave_last_renewal_summary = fields.Char(
        string='Last Renewal Summary',
        compute='_compute_sick_leave_last_renewal',
    )
    annual_leave_days_per_year = fields.Integer(
        related='company_id.annual_leave_days_per_year',
        readonly=False,
    )
    annual_leave_type_id = fields.Many2one(
        related='company_id.annual_leave_type_id',
        readonly=False,
    )
    annual_leave_last_carryover_date = fields.Datetime(
        string='Last Annual Leave Carryover',
        compute='_compute_annual_leave_last_carryover',
    )
    annual_leave_last_carryover_summary = fields.Char(
        string='Last Carryover Summary',
        compute='_compute_annual_leave_last_carryover',
    )

    @api.depends('company_id')
    def _compute_sick_leave_last_renewal(self):
        Log = self.env['hr.sick.leave.renewal.log']
        for settings in self:
            log = Log.search([
                ('company_id', '=', settings.company_id.id),
            ], order='run_date desc, id desc', limit=1)
            settings.sick_leave_last_renewal_date = log.run_date if log else False
            settings.sick_leave_last_renewal_summary = log.summary if log else False

    @api.depends('company_id')
    def _compute_annual_leave_last_carryover(self):
        Log = self.env['hr.annual.leave.carryover.log']
        for settings in self:
            log = Log.search([
                ('company_id', '=', settings.company_id.id),
            ], order='run_date desc, id desc', limit=1)
            settings.annual_leave_last_carryover_date = log.run_date if log else False
            settings.annual_leave_last_carryover_summary = log.summary if log else False

    def action_run_annual_leave_carryover(self):
        self.ensure_one()
        logs = self.env['hr.annual.leave.carryover.log']._run_carryover(
            company=self.company_id,
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

    def action_run_sick_leave_renewal(self):
        self.ensure_one()
        logs = self.env['hr.sick.leave.renewal.log']._run_renewal(
            company=self.company_id,
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

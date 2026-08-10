# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrHourlyDepartureAllocationWizard(models.TransientModel):
    _name = 'hr.hourly.departure.allocation.wizard'
    _description = 'Run Hourly Departure Monthly Allocation'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    allocation_year = fields.Integer(
        string='Year',
        required=True,
        default=lambda self: fields.Date.today().year,
    )
    allocation_month = fields.Integer(
        string='Month',
        required=True,
        default=lambda self: fields.Date.today().month,
    )

    @api.constrains('allocation_year', 'allocation_month')
    def _check_period(self):
        for wizard in self:
            if wizard.allocation_year < 2000 or wizard.allocation_year > 2100:
                raise UserError(_('Year must be between 2000 and 2100.'))
            if wizard.allocation_month < 1 or wizard.allocation_month > 12:
                raise UserError(_('Month must be between 1 and 12.'))

    def action_run_allocation(self):
        self.ensure_one()
        logs = self.env['hr.hourly.departure.allocation.log']._run_allocation(
            company=self.company_id,
            year=self.allocation_year,
            month=self.allocation_month,
            trigger='manual',
            force=True,
        )
        if not logs:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Hourly Departure Allocation'),
                    'message': _('No allocations were created or updated.'),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        log = logs[0]
        next_action = self.env['ir.actions.act_window']._for_xml_id(
            'hr_holidays_custom_ext.action_hr_hourly_departure_allocation_log'
        )
        next_action['domain'] = [('id', 'in', logs.ids)]
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Hourly Departure Allocation Complete'),
                'message': log.summary,
                'type': 'success',
                'sticky': False,
                'next': next_action,
            },
        }

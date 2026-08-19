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
    annual_leave_carryover_max_days = fields.Integer(
        related='company_id.annual_leave_carryover_max_days',
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
    overtime_leave_type_id = fields.Many2one(
        related='company_id.overtime_leave_type_id',
        readonly=False,
    )
    hourly_departure_type_id = fields.Many2one(
        related='company_id.hourly_departure_type_id',
        readonly=False,
    )
    hourly_departure_max_hours_day = fields.Float(
        related='company_id.hourly_departure_max_hours_day',
        readonly=False,
    )
    hourly_departure_max_hours_month = fields.Float(
        related='company_id.hourly_departure_max_hours_month',
        readonly=False,
    )
    hourly_departure_last_allocation_date = fields.Datetime(
        string='Last Hourly Departure Allocation',
        compute='_compute_hourly_departure_last_allocation',
    )
    hourly_departure_last_allocation_summary = fields.Char(
        string='Last Hourly Departure Summary',
        compute='_compute_hourly_departure_last_allocation',
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

    @api.depends('company_id')
    def _compute_hourly_departure_last_allocation(self):
        Log = self.env['hr.hourly.departure.allocation.log']
        for settings in self:
            log = Log.search([
                ('company_id', '=', settings.company_id.id),
            ], order='run_date desc, id desc', limit=1)
            settings.hourly_departure_last_allocation_date = log.run_date if log else False
            settings.hourly_departure_last_allocation_summary = log.summary if log else False

    def action_run_annual_leave_carryover(self):
        self.ensure_one()
        return {
            'name': _('Annual Leave Carryover'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.annual.leave.carryover.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_company_id': self.company_id.id,
            },
        }

    def action_run_sick_leave_renewal(self):
        self.ensure_one()
        return {
            'name': _('Sick Leave Renewal'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.sick.leave.renewal.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_company_id': self.company_id.id,
            },
        }

    def action_run_hourly_departure_allocation(self):
        self.ensure_one()
        return {
            'name': _('Hourly Departure Allocation'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.hourly.departure.allocation.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_company_id': self.company_id.id,
            },
        }

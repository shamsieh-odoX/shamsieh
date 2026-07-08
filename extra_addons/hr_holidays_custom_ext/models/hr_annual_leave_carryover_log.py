# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from datetime import date

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class HrAnnualLeaveCarryoverLog(models.Model):
    _name = 'hr.annual.leave.carryover.log'
    _description = 'Annual Leave Carryover Log'
    _order = 'run_date desc, id desc'

    company_id = fields.Many2one(
        'res.company',
        required=True,
        index=True,
        ondelete='cascade',
        default=lambda self: self.env.company.id,
    )
    target_year = fields.Integer(required=True, index=True)
    run_date = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    trigger = fields.Selection(
        selection=[
            ('cron', 'Scheduled'),
            ('manual', 'Manual'),
        ],
        required=True,
        default='manual',
    )
    employees_processed = fields.Integer()
    grants_created = fields.Integer()
    grants_skipped = fields.Integer()
    carryovers_created = fields.Integer()
    carryovers_skipped = fields.Integer()
    carryover_days_forfeited = fields.Float(digits=(16, 2))
    summary = fields.Text()

    def _get_company_timezone(self, company):
        if company.resource_calendar_id and company.resource_calendar_id.tz:
            return company.resource_calendar_id.tz
        return 'UTC'

    def _get_company_today(self, company):
        tz_name = self._get_company_timezone(company)
        return fields.Date.context_today(self.with_context(tz=tz_name))

    def _is_january_first(self, company):
        today = self._get_company_today(company)
        return today.month == 1 and today.day == 1

    def _get_annual_leave_type(self, company):
        leave_type = company.annual_leave_type_id
        if leave_type:
            return leave_type
        return self.env.ref('hr_holidays.leave_type_paid_time_off')

    def _find_existing_allocation(self, employee, leave_type, origin, target_year):
        return self.env['hr.leave.allocation'].sudo().search([
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', leave_type.id),
            ('allocation_origin', '=', origin),
            ('origin_year', '=', target_year),
            ('date_from', '=', date(target_year, 1, 1)),
        ], limit=1)

    def _create_and_approve_allocation(self, vals):
        allocation = self.env['hr.leave.allocation'].sudo().create(vals)
        if allocation.state != 'validate':
            allocation.action_approve()
        return allocation

    @api.model
    def _forfeit_expired_carryover(self, company, as_of_date):
        Allocation = self.env['hr.leave.allocation'].sudo()
        expired_allocations = Allocation.search([
            ('employee_id.company_id', '=', company.id),
            ('allocation_origin', '=', 'year_carryover'),
            ('state', '=', 'validate'),
            ('carried_over_days_expiration_date', '<=', as_of_date),
            ('expiring_carryover_days', '>', 0),
        ])
        forfeited_days = 0.0
        for allocation in expired_allocations:
            unused = max(0.0, allocation.number_of_days - allocation.leaves_taken)
            forfeit_days = min(unused, allocation.expiring_carryover_days)
            if forfeit_days <= 0:
                allocation.expiring_carryover_days = 0
                continue
            remaining_days = allocation.number_of_days - forfeit_days
            if remaining_days <= 0 and allocation.leaves_taken <= 0:
                allocation.action_refuse()
            else:
                allocation.write({
                    'number_of_days': max(remaining_days, allocation.leaves_taken),
                    'expiring_carryover_days': 0,
                })
            forfeited_days += forfeit_days
        return forfeited_days

    @api.model
    def _run_carryover(self, company=None, target_year=None, trigger='manual', force=False):
        BalanceSummary = self.env['hr.leave.balance.summary']
        Employee = self.env['hr.employee'].sudo()

        if company:
            companies = company
        else:
            companies = self.env['res.company'].sudo().search([])

        logs = self.env['hr.annual.leave.carryover.log']
        for comp in companies:
            if trigger == 'cron' and not force and not self._is_january_first(comp):
                continue

            leave_type = self._get_annual_leave_type(comp)
            if not leave_type:
                continue

            run_year = target_year or self._get_company_today(comp).year
            ending_year = run_year - 1
            as_of_date = date(ending_year, 12, 31)
            year_start = date(run_year, 1, 1)
            year_end = date(run_year, 12, 31)
            grant_days = comp.annual_leave_days_per_year or 21

            forfeited_days = self._forfeit_expired_carryover(comp, as_of_date)

            employees = Employee.search([
                ('company_id', '=', comp.id),
                ('active', '=', True),
            ])

            grants_created = 0
            grants_skipped = 0
            carryovers_created = 0
            carryovers_skipped = 0

            employee_balances = []
            for employee in employees:
                balance_row = BalanceSummary._get_balance_row(employee, leave_type, as_of_date)
                carryover_days = balance_row['current_year_balance'] if balance_row else 0.0
                employee_balances.append((employee, carryover_days))

            for employee, carryover_days in employee_balances:
                if self._find_existing_allocation(employee, leave_type, 'annual_grant', run_year):
                    grants_skipped += 1
                else:
                    self._create_and_approve_allocation({
                        'name': _('Annual Leave %s', run_year),
                        'employee_id': employee.id,
                        'holiday_status_id': leave_type.id,
                        'allocation_type': 'regular',
                        'allocation_origin': 'annual_grant',
                        'origin_year': run_year,
                        'number_of_days': grant_days,
                        'date_from': year_start,
                        'date_to': year_end,
                    })
                    grants_created += 1

                if carryover_days <= 0:
                    continue

                if self._find_existing_allocation(employee, leave_type, 'year_carryover', run_year):
                    carryovers_skipped += 1
                    continue

                self._create_and_approve_allocation({
                    'name': _('Carryover from %s', ending_year),
                    'employee_id': employee.id,
                    'holiday_status_id': leave_type.id,
                    'allocation_type': 'regular',
                    'allocation_origin': 'year_carryover',
                    'origin_year': run_year,
                    'number_of_days': carryover_days,
                    'expiring_carryover_days': carryover_days,
                    'carried_over_days_expiration_date': year_end,
                    'date_from': year_start,
                    'date_to': year_end,
                })
                carryovers_created += 1

            summary = _(
                'Annual leave carryover for %(company)s (%(year)s): '
                '%(processed)s employees processed, '
                '%(grants_created)s grants created, %(grants_skipped)s grants skipped, '
                '%(carryovers_created)s carryovers created, %(carryovers_skipped)s carryovers skipped, '
                '%(forfeited)s carryover days forfeited.',
                company=comp.name,
                year=run_year,
                processed=len(employees),
                grants_created=grants_created,
                grants_skipped=grants_skipped,
                carryovers_created=carryovers_created,
                carryovers_skipped=carryovers_skipped,
                forfeited=forfeited_days,
            )
            _logger.info(summary)
            logs += self.sudo().create({
                'company_id': comp.id,
                'target_year': run_year,
                'run_date': fields.Datetime.now(),
                'trigger': trigger,
                'employees_processed': len(employees),
                'grants_created': grants_created,
                'grants_skipped': grants_skipped,
                'carryovers_created': carryovers_created,
                'carryovers_skipped': carryovers_skipped,
                'carryover_days_forfeited': forfeited_days,
                'summary': summary,
            })

        return logs

    @api.model
    def _cron_carry_forward_annual_leave(self):
        return self._run_carryover(trigger='cron', force=False)

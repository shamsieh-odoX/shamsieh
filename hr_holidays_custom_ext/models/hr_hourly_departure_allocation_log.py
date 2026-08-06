# Part of Odoo. See LICENSE file for full copyright and licensing details.

import calendar
import logging
from datetime import date

from odoo import _, api, fields, models
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)


class HrHourlyDepartureAllocationLog(models.Model):
    _name = 'hr.hourly.departure.allocation.log'
    _description = 'Hourly Departure Monthly Allocation Log'
    _order = 'run_date desc, id desc'

    company_id = fields.Many2one(
        'res.company',
        required=True,
        index=True,
        ondelete='cascade',
        default=lambda self: self.env.company.id,
    )
    allocation_year = fields.Integer(required=True, index=True)
    allocation_month = fields.Integer(required=True, index=True)
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
    allocations_created = fields.Integer()
    allocations_skipped = fields.Integer()
    summary = fields.Text()

    def _get_company_timezone(self, company):
        if company.resource_calendar_id and company.resource_calendar_id.tz:
            return company.resource_calendar_id.tz
        return 'UTC'

    def _get_company_today(self, company):
        tz_name = self._get_company_timezone(company)
        return fields.Date.context_today(self.with_context(tz=tz_name))

    def _is_first_of_month(self, company):
        today = self._get_company_today(company)
        return today.day == 1

    def _get_departure_type(self, company):
        return company._get_hourly_departure_type()

    def _find_existing_allocation(self, employee, leave_type, year, month, month_start):
        Allocation = self.env['hr.leave.allocation'].sudo()
        existing = Allocation.search([
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', leave_type.id),
            ('allocation_origin', '=', 'hourly_departure_monthly'),
            ('origin_year', '=', year),
            ('origin_month', '=', month),
        ], limit=1)
        if existing:
            return existing
        return Allocation.search([
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', leave_type.id),
            ('date_from', '=', month_start),
            ('allocation_origin', '=', 'hourly_departure_monthly'),
        ], limit=1)

    def _hours_to_days(self, employee, hours, reference_date):
        hours_per_day = employee._get_hours_per_day(reference_date) or 8.0
        if float_compare(hours_per_day, 0.0, precision_digits=2) <= 0:
            hours_per_day = 8.0
        return hours / hours_per_day

    @api.model
    def _run_allocation(self, company=None, year=None, month=None, trigger='manual', force=False):
        Allocation = self.env['hr.leave.allocation'].sudo()
        Employee = self.env['hr.employee'].sudo()

        if company:
            companies = company
        else:
            companies = self.env['res.company'].sudo().search([])

        logs = self.env['hr.hourly.departure.allocation.log']
        for comp in companies:
            if trigger == 'cron' and not force and not self._is_first_of_month(comp):
                continue

            today = self._get_company_today(comp)
            allocation_year = year or today.year
            allocation_month = month or today.month
            if allocation_month < 1 or allocation_month > 12:
                continue

            leave_type = self._get_departure_type(comp)
            if not leave_type:
                _logger.warning(
                    'Skipping hourly departure allocation for %s: no leave type configured.',
                    comp.name,
                )
                continue

            month_start = date(allocation_year, allocation_month, 1)
            month_end = date(
                allocation_year,
                allocation_month,
                calendar.monthrange(allocation_year, allocation_month)[1],
            )
            hours = comp.hourly_departure_max_hours_month or 6.0

            employees = Employee.search([
                ('company_id', '=', comp.id),
                ('active', '=', True),
            ])

            created = 0
            skipped = 0
            for employee in employees:
                existing = self._find_existing_allocation(
                    employee, leave_type, allocation_year, allocation_month, month_start,
                )
                if existing:
                    skipped += 1
                    continue

                number_of_days = self._hours_to_days(employee, hours, month_start)
                allocation = Allocation.create({
                    'name': _(
                        'Hourly Departure %(month)02d/%(year)s',
                        month=allocation_month,
                        year=allocation_year,
                    ),
                    'employee_id': employee.id,
                    'holiday_status_id': leave_type.id,
                    'allocation_type': 'regular',
                    'allocation_origin': 'hourly_departure_monthly',
                    'origin_year': allocation_year,
                    'origin_month': allocation_month,
                    'number_of_days': number_of_days,
                    'date_from': month_start,
                    'date_to': month_end,
                })
                if allocation.state != 'validate':
                    allocation.action_approve()
                created += 1

            summary = _(
                'Hourly departure allocation for %(company)s (%(month)02d/%(year)s): '
                '%(processed)s employees processed, '
                '%(created)s allocations created, '
                '%(skipped)s skipped.',
                company=comp.name,
                month=allocation_month,
                year=allocation_year,
                processed=len(employees),
                created=created,
                skipped=skipped,
            )
            _logger.info(summary)
            logs += self.sudo().create({
                'company_id': comp.id,
                'allocation_year': allocation_year,
                'allocation_month': allocation_month,
                'run_date': fields.Datetime.now(),
                'trigger': trigger,
                'employees_processed': len(employees),
                'allocations_created': created,
                'allocations_skipped': skipped,
                'summary': summary,
            })

        return logs

    @api.model
    def _cron_allocate_hourly_departure(self):
        return self._run_allocation(trigger='cron', force=False)

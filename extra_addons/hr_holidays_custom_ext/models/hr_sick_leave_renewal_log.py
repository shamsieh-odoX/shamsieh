# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from datetime import date

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class HrSickLeaveRenewalLog(models.Model):
    _name = 'hr.sick.leave.renewal.log'
    _description = 'Sick Leave Renewal Log'
    _order = 'run_date desc, id desc'

    company_id = fields.Many2one(
        'res.company',
        required=True,
        index=True,
        ondelete='cascade',
        default=lambda self: self.env.company.id,
    )
    renewal_year = fields.Integer(required=True, index=True)
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

    def _is_january_first(self, company):
        today = self._get_company_today(company)
        return today.month == 1 and today.day == 1

    def _get_sick_leave_type(self):
        return self.env.ref('hr_holidays_custom_ext.leave_type_sick_leave')

    @api.model
    def _run_renewal(self, company=None, year=None, trigger='manual', force=False):
        sick_type = self._get_sick_leave_type()
        Allocation = self.env['hr.leave.allocation'].sudo()
        Employee = self.env['hr.employee'].sudo()

        if company:
            companies = company
        else:
            companies = self.env['res.company'].sudo().search([])

        logs = self.env['hr.sick.leave.renewal.log']
        for comp in companies:
            if trigger == 'cron' and not force and not self._is_january_first(comp):
                continue

            renewal_year = year or self._get_company_today(comp).year
            year_start = date(renewal_year, 1, 1)
            year_end = date(renewal_year, 12, 31)
            days_per_year = comp.sick_leave_days_per_year or 14

            employees = Employee.search([
                ('company_id', '=', comp.id),
                ('active', '=', True),
            ])

            created = 0
            skipped = 0
            for employee in employees:
                existing = Allocation.search([
                    ('employee_id', '=', employee.id),
                    ('holiday_status_id', '=', sick_type.id),
                    ('date_from', '=', year_start),
                ], limit=1)
                if existing:
                    skipped += 1
                    continue

                allocation = Allocation.create({
                    'name': _('Sick Leave %s', renewal_year),
                    'employee_id': employee.id,
                    'holiday_status_id': sick_type.id,
                    'allocation_type': 'regular',
                    'number_of_days': days_per_year,
                    'date_from': year_start,
                    'date_to': year_end,
                })
                if allocation.state != 'validate':
                    allocation.action_approve()
                created += 1

            summary = _(
                'Sick leave renewal for %(company)s (%(year)s): '
                '%(processed)s employees processed, '
                '%(created)s allocations created, '
                '%(skipped)s skipped.',
                company=comp.name,
                year=renewal_year,
                processed=len(employees),
                created=created,
                skipped=skipped,
            )
            _logger.info(summary)
            logs += self.sudo().create({
                'company_id': comp.id,
                'renewal_year': renewal_year,
                'run_date': fields.Datetime.now(),
                'trigger': trigger,
                'employees_processed': len(employees),
                'allocations_created': created,
                'allocations_skipped': skipped,
                'summary': summary,
            })

        return logs

    @api.model
    def _cron_renew_sick_leave_allocations(self):
        return self._run_renewal(trigger='cron', force=False)

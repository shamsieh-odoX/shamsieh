# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from datetime import date

from odoo import _, api, models
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)


class HrOvertimeLeaveHelper(models.AbstractModel):
    """Shared helper for creating / reversing overtime Time Off allocations."""

    _name = 'hr.overtime.leave.helper'
    _description = 'Overtime Leave Allocation Helper'

    @api.model
    def _get_overtime_leave_type(self, company):
        return company._get_overtime_leave_type()

    @api.model
    def _hours_to_days(self, employee, hours, reference_date=None):
        reference_date = reference_date or date.today()
        hours_per_day = employee._get_hours_per_day(reference_date) or 8.0
        if float_compare(hours_per_day, 0.0, precision_digits=2) <= 0:
            hours_per_day = 8.0
        return hours / hours_per_day

    @api.model
    def create_overtime_allocation(
        self, employee, hours, origin, year=None,
        overtime_request=None,
    ):
        """Create a validated allocation on the Overtime leave type.

        Returns the allocation record or False if no leave type is configured.
        """
        company = employee.company_id or self.env.company
        leave_type = self._get_overtime_leave_type(company)
        if not leave_type:
            _logger.warning(
                'No overtime leave type configured for %s; skipping allocation.',
                company.name,
            )
            return False

        ref_date = date.today()
        year = year or ref_date.year
        number_of_days = self._hours_to_days(employee, hours, ref_date)
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        vals = {
            'name': _('Overtime %(hours).1fh', hours=hours),
            'employee_id': employee.id,
            'holiday_status_id': leave_type.id,
            'allocation_type': 'regular',
            'allocation_origin': origin,
            'origin_year': year,
            'number_of_days': number_of_days,
            'date_from': year_start,
            'date_to': year_end,
        }
        if overtime_request:
            vals['overtime_request_id'] = overtime_request.id
            vals['name'] = _(
                'Overtime %(ref)s (%(hours).1fh)',
                ref=overtime_request.name,
                hours=hours,
            )
        Allocation = self.env['hr.leave.allocation'].sudo()
        allocation = Allocation.create(vals)
        if allocation.state != 'validate':
            allocation.action_approve()
        return allocation

    @api.model
    def reverse_overtime_allocation(self, allocation):
        """Cancel/refuse an overtime allocation if no hours have been taken."""
        if not allocation or allocation.state not in ('validate', 'confirm'):
            return False
        leaves_taken = allocation.leaves_taken if hasattr(allocation, 'leaves_taken') else 0.0
        if float_compare(leaves_taken, 0.0, precision_digits=2) > 0:
            _logger.info(
                'Cannot reverse allocation %s: %.1f days already taken.',
                allocation.display_name,
                leaves_taken,
            )
            return False
        allocation.action_refuse()
        return True

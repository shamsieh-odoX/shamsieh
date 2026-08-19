# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import _, models

_logger = logging.getLogger(__name__)


class HrOvertimeRequest(models.Model):
    _inherit = 'hr.overtime.request'

    def _on_approval_complete(self):
        super()._on_approval_complete()
        Helper = self.env['hr.overtime.leave.helper']
        for request in self:
            existing = self.env['hr.leave.allocation'].sudo().search([
                ('overtime_request_id', '=', request.id),
                ('allocation_origin', '=', 'overtime_request'),
                ('state', '=', 'validate'),
            ], limit=1)
            if existing:
                continue
            hours = request.overtime_hours
            if hours <= 0:
                continue
            allocation = Helper.create_overtime_allocation(
                employee=request.employee_id,
                hours=hours,
                origin='overtime_request',
                overtime_request=request,
            )
            if allocation:
                request.sudo().message_post(
                    body=_(
                        '%(hours).1f overtime hours added to Time Off balance.',
                        hours=hours,
                    ),
                )

    def _on_approval_refused(self, line, reason):
        super()._on_approval_refused(line, reason)
        self._reverse_overtime_allocations()

    def _reverse_overtime_allocations(self):
        Helper = self.env['hr.overtime.leave.helper']
        for request in self:
            allocations = self.env['hr.leave.allocation'].sudo().search([
                ('overtime_request_id', '=', request.id),
                ('allocation_origin', '=', 'overtime_request'),
                ('state', '=', 'validate'),
            ])
            for alloc in allocations:
                if Helper.reverse_overtime_allocation(alloc):
                    request.sudo().message_post(
                        body=_('Overtime Time Off allocation reversed.'),
                    )
                else:
                    request.sudo().message_post(
                        body=_(
                            'Could not reverse overtime allocation — '
                            'hours may already be taken.'
                        ),
                    )

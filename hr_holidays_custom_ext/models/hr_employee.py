# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def _get_consumed_leaves(self, leave_types, target_date=False, ignore_future=False):
        """Available days must not drop until the leave is fully approved.

        Standard Odoo subtracts pending requests (confirm / validate1) from
        ``virtual_remaining_leaves``, so "21 days available" becomes 20 as soon
        as the employee applies. Company policy: only validated leaves consume
        the balance shown to employees and used for remaining days.
        """
        consumed, excess = super()._get_consumed_leaves(
            leave_types, target_date=target_date, ignore_future=ignore_future,
        )
        for employee_map in consumed.values():
            for leave_type_map in employee_map.values():
                for allocation_data in leave_type_map.values():
                    # Align virtual figures with validated-only figures.
                    allocation_data['virtual_leaves_taken'] = allocation_data.get('leaves_taken', 0)
                    allocation_data['virtual_remaining_leaves'] = allocation_data.get('remaining_leaves', 0)
        for employee_map in excess.values():
            for leave_type_data in employee_map.values():
                for day_data in leave_type_data.get('excess_days', {}).values():
                    # Pending excess should not look like taken balance.
                    if day_data.get('is_virtual'):
                        day_data['amount'] = 0
        return consumed, excess

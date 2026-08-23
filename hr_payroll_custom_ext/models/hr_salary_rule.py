# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models

from odoo.addons.hr_payroll_custom_ext.hooks import _link_rules_to_structures


class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'

    @api.model
    def _link_custom_deduction_rules(self):
        """Attach custom deduction rules to available payroll structures."""
        _link_rules_to_structures(self.env)

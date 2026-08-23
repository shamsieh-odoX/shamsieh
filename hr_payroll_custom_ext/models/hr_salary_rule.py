# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models

from ..hooks import _ensure_custom_deduction_rules


class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'

    @api.model
    def _link_custom_deduction_rules(self):
        """Create/update custom deduction rules on available structures."""
        _ensure_custom_deduction_rules(self.env)

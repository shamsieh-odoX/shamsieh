# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    overtime_link_to_payroll = fields.Boolean(
        related='company_id.overtime_link_to_payroll',
        readonly=False,
    )

# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    overtime_link_to_payroll = fields.Boolean(
        string='Link Overtime to Payroll',
        default=False,
    )

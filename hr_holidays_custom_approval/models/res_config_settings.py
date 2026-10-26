# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    time_off_gm_id = fields.Many2one(
        related='company_id.time_off_gm_id',
        readonly=False,
        string='Time Off General Manager',
    )

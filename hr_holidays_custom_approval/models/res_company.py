# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    time_off_gm_id = fields.Many2one(
        'hr.employee',
        string='Time Off General Manager',
        help='Employee who performs the second approval when the requester has no manager '
             'in the org chart (parent_id). Prefer an employee linked to a user.',
    )

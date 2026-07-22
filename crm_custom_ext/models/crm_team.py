# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class CrmTeam(models.Model):
    _inherit = 'crm.team'

    country_id = fields.Many2one(
        'res.country',
        string='Country',
        help='Country served by this sales team. Used to auto-assign leads.',
    )
    target_ids = fields.One2many(
        'crm.team.target',
        'team_id',
        string='Targets',
    )

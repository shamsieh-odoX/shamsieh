# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class CrmLeadSector(models.Model):
    _name = 'crm.lead.sector'
    _description = 'CRM Lead Sector'
    _order = 'sequence, name'

    name = fields.Char(string='Sector', required=True, translate=True)
    code = fields.Char(
        string='Code',
        copy=False,
        index=True,
        help='Internal reference used when migrating legacy sector values.',
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    lead_count = fields.Integer(compute='_compute_lead_count')

    _name_uniq = models.Constraint(
        'unique(name)',
        'Sector name must be unique.',
    )

    @api.depends()
    def _compute_lead_count(self):
        if not self.ids:
            self.lead_count = 0
            return
        grouped = self.env['crm.lead']._read_group(
            [('sector_id', 'in', self.ids)],
            ['sector_id'],
            ['__count'],
        )
        counts = {sector.id: count for sector, count in grouped}
        for sector in self:
            sector.lead_count = counts.get(sector.id, 0)

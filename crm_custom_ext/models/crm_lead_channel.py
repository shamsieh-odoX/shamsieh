# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class CrmLeadChannel(models.Model):
    _name = 'crm.lead.channel'
    _description = 'CRM Lead Channel'
    _order = 'sequence, name'

    name = fields.Char(string='Channel', required=True, translate=True)
    code = fields.Char(
        string='Code',
        copy=False,
        index=True,
        help='Internal reference used when migrating legacy channel values.',
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    lead_count = fields.Integer(compute='_compute_lead_count')

    _name_uniq = models.Constraint(
        'unique(name)',
        'Channel name must be unique.',
    )

    @api.depends()
    def _compute_lead_count(self):
        if not self.ids:
            self.lead_count = 0
            return
        grouped = self.env['crm.lead']._read_group(
            [('channel_id', 'in', self.ids)],
            ['channel_id'],
            ['__count'],
        )
        counts = {channel.id: count for channel, count in grouped}
        for channel in self:
            channel.lead_count = counts.get(channel.id, 0)

    @api.model
    def _get_or_create_by_name(self, name):
        name = (name or '').strip()
        if not name:
            return self.browse()
        channel = self.search([('name', '=ilike', name)], limit=1)
        if channel:
            return channel
        return self.create({'name': name})

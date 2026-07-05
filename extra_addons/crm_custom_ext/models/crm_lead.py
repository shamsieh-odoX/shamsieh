# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

INTEREST_LEVEL_SELECTION = [
    ('hot', 'Hot'),
    ('warm', 'Warm'),
    ('cold', 'Cold'),
    ('not_interested', 'Not Interested'),
]


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    lead_ref = fields.Char(
        string='Lead ID',
        readonly=True,
        copy=False,
        index=True,
    )
    sector_id = fields.Many2one(
        'crm.lead.sector',
        string='Sector',
        tracking=True,
        ondelete='set null',
        index=True,
    )
    channel_id = fields.Many2one(
        'crm.lead.channel',
        string='Channel',
        tracking=True,
        ondelete='set null',
        index=True,
    )
    interest_level = fields.Selection(
        INTEREST_LEVEL_SELECTION,
        string='Interest Level',
        tracking=True,
    )
    first_contact_date = fields.Date(
        string='First Contact Date',
        tracking=True,
    )
    last_contact_date = fields.Date(
        string='Last Contact Date',
        tracking=True,
    )
    next_followup_date = fields.Date(
        string='Next Follow-up Date',
        tracking=True,
    )
    demo_date = fields.Date(
        string='Demo Date',
        tracking=True,
    )
    proposal_sent_date = fields.Date(
        string='Proposal Sent Date',
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('lead_ref'):
                vals['lead_ref'] = self.env['ir.sequence'].next_by_code('crm.lead.ref') or '/'
            lead_type = vals.get('type')
            if not lead_type:
                lead_type = 'lead' if self.env.user.has_group('crm.group_use_lead') else 'opportunity'
            if lead_type == 'lead':
                vals.setdefault('first_contact_date', fields.Date.context_today(self))
            self._apply_team_from_country_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        if 'country_id' in vals and 'team_id' not in vals:
            team_vals = {}
            self._apply_team_from_country_vals(team_vals, country_id=vals['country_id'])
            if team_vals.get('team_id'):
                vals = dict(vals, team_id=team_vals['team_id'])
        result = super().write(vals)
        if any(key in vals for key in ('activity_ids', 'activity_date_deadline')):
            self._sync_next_followup_from_activities()
        return result

    @api.onchange('country_id')
    def _onchange_country_id_team(self):
        team_vals = {}
        self._apply_team_from_country_vals(team_vals, country_id=self.country_id.id if self.country_id else False)
        if team_vals.get('team_id'):
            self.team_id = team_vals['team_id']

    def _apply_team_from_country_vals(self, vals, country_id=None):
        country = country_id if country_id is not None else vals.get('country_id')
        if not country:
            return
        team = self.env['crm.team'].search([('country_id', '=', country)], limit=1)
        if not team:
            team = self.env.ref('crm_custom_ext.crm_team_other', raise_if_not_found=False)
        if team:
            vals['team_id'] = team.id

    def _sync_next_followup_from_activities(self):
        today = fields.Date.context_today(self)
        for lead in self:
            deadlines = lead.activity_ids.filtered('date_deadline').mapped('date_deadline')
            if deadlines:
                lead.next_followup_date = min(deadlines)
            elif not lead.next_followup_date:
                lead.next_followup_date = False

    def message_post(self, **kwargs):
        result = super().message_post(**kwargs)
        if kwargs.get('message_type', 'comment') != 'notification':
            self.filtered(lambda l: l.type in ('lead', 'opportunity')).write({
                'last_contact_date': fields.Date.context_today(self),
            })
        return result

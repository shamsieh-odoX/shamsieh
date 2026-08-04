# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta

from odoo import api, fields, models


class CrmTeamTarget(models.Model):
    _name = 'crm.team.target'
    _description = 'Sales Team Target'
    _order = 'date_start desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    team_id = fields.Many2one(
        'crm.team',
        string='Sales Team',
        required=True,
        ondelete='cascade',
        index=True,
    )
    country_id = fields.Many2one(
        related='team_id.country_id',
        string='Country',
        store=True,
        readonly=True,
    )
    period = fields.Selection(
        [
            ('monthly', 'Monthly'),
            ('quarterly', 'Quarterly'),
            ('yearly', 'Yearly'),
        ],
        string='Target Period',
        required=True,
        default='monthly',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    target_amount = fields.Monetary(
        string='Target Amount',
        currency_field='currency_id',
        required=True,
    )
    date_start = fields.Date(string='Target Start Date', required=True)
    date_end = fields.Date(string='Target End Date', required=True)
    actual_won_revenue = fields.Monetary(
        string='Actual Won Revenue',
        currency_field='currency_id',
        compute='_compute_performance',
    )
    expected_revenue_total = fields.Monetary(
        string='Expected Revenue',
        currency_field='currency_id',
        compute='_compute_performance',
    )
    achievement_pct = fields.Float(
        string='Achievement %',
        compute='_compute_performance',
        digits=(16, 2),
    )
    remaining_target = fields.Monetary(
        string='Remaining to Target',
        currency_field='currency_id',
        compute='_compute_performance',
    )
    company_id = fields.Many2one(
        related='team_id.company_id',
        store=True,
        readonly=True,
    )

    @api.depends('team_id', 'period', 'date_start', 'date_end', 'target_amount', 'currency_id')
    def _compute_name(self):
        period_labels = dict(self._fields['period'].selection)
        for target in self:
            if target.team_id and target.date_start:
                target.name = '%s - %s (%s)' % (
                    target.team_id.name,
                    period_labels.get(target.period, target.period),
                    target.date_start,
                )
            else:
                target.name = 'New Target'

    @api.depends(
        'team_id',
        'date_start',
        'date_end',
        'target_amount',
        'currency_id',
    )
    def _compute_performance(self):
        Lead = self.env['crm.lead']
        for target in self:
            actual = expected = 0.0
            if target.team_id and target.date_start and target.date_end:
                start_dt = fields.Datetime.to_datetime(target.date_start)
                end_dt = fields.Datetime.to_datetime(target.date_end) + timedelta(days=1, seconds=-1)
                won_domain = [
                    ('team_id', '=', target.team_id.id),
                    ('won_status', '=', 'won'),
                    ('date_closed', '>=', start_dt),
                    ('date_closed', '<=', end_dt),
                ]
                won_leads = Lead.search(won_domain)
                for lead in won_leads:
                    actual += target.currency_id._convert(
                        lead.expected_revenue,
                        target.currency_id,
                        target.company_id or self.env.company,
                        lead.date_closed.date() if lead.date_closed else fields.Date.today(),
                    )

                open_domain = [
                    ('team_id', '=', target.team_id.id),
                    ('won_status', '=', 'pending'),
                    ('active', '=', True),
                    ('create_date', '>=', start_dt),
                    ('create_date', '<=', end_dt),
                ]
                open_leads = Lead.search(open_domain)
                for lead in open_leads:
                    expected += target.currency_id._convert(
                        lead.prorated_revenue,
                        target.currency_id,
                        target.company_id or self.env.company,
                        fields.Date.today(),
                    )

            target.actual_won_revenue = actual
            target.expected_revenue_total = expected
            if target.target_amount:
                target.achievement_pct = (actual / target.target_amount) * 100.0
                target.remaining_target = max(target.target_amount - actual, 0.0)
            else:
                target.achievement_pct = 0.0
                target.remaining_target = 0.0

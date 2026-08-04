# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FingerprintAttendancePolicy(models.Model):
    _name = 'fingerprint.attendance.policy'
    _description = 'Fingerprint Attendance Policy'
    _order = 'company_id, name'

    name = fields.Char(required=True, default='Default Attendance Policy')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)
    is_company_default = fields.Boolean(string='Company Default')
    duplicate_scan_window_minutes = fields.Integer(default=3)
    minimum_checkout_gap_minutes = fields.Integer(default=30)
    max_shift_hours = fields.Float(default=16.0)
    allow_multiple_attendances_per_day = fields.Boolean(default=False)
    allow_overnight_shift = fields.Boolean(default=False)
    process_mode = fields.Selection(
        selection=[
            ('first_last', 'First / Last Scan'),
            ('alternating_in_out', 'Alternating In / Out'),
        ],
        default='first_last',
        required=True,
    )
    ignore_middle_scans = fields.Boolean(default=True)
    late_grace_minutes = fields.Integer(
        default=15,
        help='Minutes after scheduled start before lateness is counted. '
             'Example: start 08:00 with 15 minutes grace => late after 08:15. '
             'Check-in at 08:20 is 5 late minutes.',
    )
    early_checkout_grace_minutes = fields.Integer(default=0)
    missing_checkout_tolerance_minutes = fields.Integer(default=60)
    raw_payload_retention_days = fields.Integer(
        default=90,
        help='Days to keep raw_payload on device logs before clearing (0 = keep forever).',
    )

    @api.constrains('is_company_default', 'company_id')
    def _check_single_company_default(self):
        for policy in self.filtered('is_company_default'):
            other = self.search([
                ('company_id', '=', policy.company_id.id),
                ('is_company_default', '=', True),
                ('id', '!=', policy.id),
            ])
            if other:
                raise ValidationError(_(
                    'Company %(company)s already has a default policy (%(policy)s).',
                    company=policy.company_id.name,
                    policy=other[0].name,
                ))

    @api.model
    def _default_policy_vals(self, company):
        return {
            'name': _('Default Attendance Policy'),
            'company_id': company.id,
            'is_company_default': True,
            'process_mode': 'first_last',
            'duplicate_scan_window_minutes': 3,
            'minimum_checkout_gap_minutes': 30,
            'max_shift_hours': 16.0,
            'allow_multiple_attendances_per_day': False,
            'allow_overnight_shift': False,
            'ignore_middle_scans': True,
            'late_grace_minutes': 15,
            'early_checkout_grace_minutes': 0,
            'missing_checkout_tolerance_minutes': 60,
        }

    @api.model
    def get_company_default(self, company):
        company = company or self.env.company
        policy = self.search([
            ('company_id', '=', company.id),
            ('is_company_default', '=', True),
            ('active', '=', True),
        ], limit=1)
        if not policy:
            policy = self.create(self._default_policy_vals(company))
        return policy

    @api.model
    def create_default_for_company(self, company):
        existing = self.search([
            ('company_id', '=', company.id),
            ('is_company_default', '=', True),
        ], limit=1)
        if existing:
            return existing
        return self.create(self._default_policy_vals(company))

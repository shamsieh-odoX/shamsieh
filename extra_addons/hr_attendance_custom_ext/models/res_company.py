# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    missing_checkout_tolerance_hours = fields.Float(
        string='Missing Checkout Tolerance (hours)',
        default=1.0,
        help='Hours after scheduled calendar end before an open attendance is flagged as missing checkout.',
    )
    face_match_threshold = fields.Float(
        string='Face Match Threshold',
        default=0.85,
        help='Minimum confidence score for face verification. Needs confirmation with provider.',
    )
    face_geo_radius_meters = fields.Integer(
        string='Face Geo Radius (meters)',
        default=500,
        help='Allowed geolocation variance for remote face attendance. Needs confirmation.',
    )
    face_attendance_stub_enabled = fields.Boolean(
        string='Enable Face Attendance Stub',
        default=False,
        help='Development only: auto-pass face verification without external provider.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        Policy = self.env['fingerprint.attendance.policy']
        for company in companies:
            Policy.create_default_for_company(company)
        return companies

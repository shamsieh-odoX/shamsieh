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
        help='Minimum cosine similarity score required for face verification.',
    )
    office_geo_latitude = fields.Float(
        string='Office Latitude',
        digits=(10, 7),
        help='Reference latitude for office check-in geofencing.',
    )
    office_geo_longitude = fields.Float(
        string='Office Longitude',
        digits=(10, 7),
        help='Reference longitude for office check-in geofencing.',
    )
    office_geo_radius_meters = fields.Integer(
        string='Office Geo Radius (meters)',
        default=500,
        help='Allowed geolocation distance in meters from the office reference point.',
    )
    face_provider = fields.Selection(
        selection=[('insightface', 'InsightFace (self-hosted)')],
        string='Face Provider',
        default='insightface',
        required=True,
    )
    face_store_raw_images = fields.Boolean(
        string='Store Raw Face Images',
        default=False,
        help='When enabled, enrollment images may be stored as attachments.',
    )
    face_quality_check_enabled = fields.Boolean(
        string='Face Quality Checks',
        default=True,
        help='Reject blurry, low-resolution, or small-face images.',
    )
    face_liveness_required = fields.Boolean(
        string='Liveness Required',
        default=False,
        help='Reserved for future advanced liveness detection.',
    )
    face_attendance_stub_enabled = fields.Boolean(
        string='Enable Face Attendance Stub',
        default=False,
        help='Development only: auto-pass face verification without external provider.',
    )
    remote_work_requests_enabled = fields.Boolean(
        string='Remote Work Requests',
        default=True,
        help='Allow employees to request ad-hoc work-from-home days with manager and HR approval.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        Policy = self.env['fingerprint.attendance.policy']
        for company in companies:
            Policy.create_default_for_company(company)
        return companies

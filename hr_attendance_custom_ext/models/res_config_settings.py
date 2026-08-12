# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    missing_checkout_tolerance_hours = fields.Float(
        related='company_id.missing_checkout_tolerance_hours',
        readonly=False,
    )
    face_attendance_stub_enabled = fields.Boolean(
        related='company_id.face_attendance_stub_enabled',
        readonly=False,
    )
    face_match_threshold = fields.Float(
        related='company_id.face_match_threshold',
        readonly=False,
    )
    office_geo_latitude = fields.Float(
        related='company_id.office_geo_latitude',
        readonly=False,
    )
    office_geo_longitude = fields.Float(
        related='company_id.office_geo_longitude',
        readonly=False,
    )
    office_geo_radius_meters = fields.Integer(
        related='company_id.office_geo_radius_meters',
        readonly=False,
    )
    face_provider = fields.Selection(
        related='company_id.face_provider',
        readonly=False,
    )
    face_store_raw_images = fields.Boolean(
        related='company_id.face_store_raw_images',
        readonly=False,
    )
    face_quality_check_enabled = fields.Boolean(
        related='company_id.face_quality_check_enabled',
        readonly=False,
    )
    face_liveness_required = fields.Boolean(
        related='company_id.face_liveness_required',
        readonly=False,
    )
    remote_work_requests_enabled = fields.Boolean(
        related='company_id.remote_work_requests_enabled',
        readonly=False,
    )

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
    face_geo_radius_meters = fields.Integer(
        related='company_id.face_geo_radius_meters',
        readonly=False,
    )

# -*- coding: utf-8 -*-

from odoo import fields, models

_ATTENDANCE_OFFICER = 'hr_attendance.group_hr_attendance_officer'


class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    # hr.employee form/search views are also opened as public profiles for users
    # without HR access (attendance officers, kiosk, directory). Fields must
    # exist on this model or Odoo raises AccessError on read.
    hikvision_presence_status = fields.Selection(
        related='employee_id.hikvision_presence_status',
        readonly=True,
    )
    live_check_in = fields.Datetime(
        related='employee_id.live_check_in',
        readonly=True,
    )
    current_break_start = fields.Datetime(
        related='employee_id.current_break_start',
        readonly=True,
    )
    current_break_hours = fields.Float(
        related='employee_id.current_break_hours',
        readonly=True,
    )
    break_count = fields.Integer(
        related='employee_id.break_count',
        readonly=True,
    )
    biometric_device_user_id = fields.Char(
        related='employee_id.biometric_device_user_id',
        groups=_ATTENDANCE_OFFICER,
        readonly=False,
    )
    face_reference_id = fields.Char(
        related='employee_id.face_reference_id',
        groups=_ATTENDANCE_OFFICER,
        readonly=False,
    )
    face_template_id = fields.Char(
        related='employee_id.face_template_id',
        groups=_ATTENDANCE_OFFICER,
        readonly=True,
    )
    face_enrollment_status = fields.Selection(
        related='employee_id.face_enrollment_status',
        groups=_ATTENDANCE_OFFICER,
        readonly=True,
    )
    face_enrolled_at = fields.Datetime(
        related='employee_id.face_enrolled_at',
        groups=_ATTENDANCE_OFFICER,
        readonly=True,
    )
    face_enrolled_by = fields.Many2one(
        related='employee_id.face_enrolled_by',
        groups=_ATTENDANCE_OFFICER,
        readonly=True,
    )
    face_template_ids = fields.One2many(
        related='employee_id.face_template_ids',
        groups=_ATTENDANCE_OFFICER,
        readonly=True,
    )
    active_face_template_id = fields.Many2one(
        related='employee_id.active_face_template_id',
        groups=_ATTENDANCE_OFFICER,
        readonly=True,
    )
    attendance_face_image_preview = fields.Binary(
        related='employee_id.attendance_face_image_preview',
        groups=_ATTENDANCE_OFFICER,
        readonly=True,
    )
    attendance_required = fields.Boolean(
        related='employee_id.attendance_required',
        groups=_ATTENDANCE_OFFICER,
        readonly=False,
    )
    remote_attendance_allowed = fields.Boolean(
        related='employee_id.remote_attendance_allowed',
        groups=_ATTENDANCE_OFFICER,
        readonly=False,
    )
    attendance_home_pin_hash = fields.Char(
        related='employee_id.attendance_home_pin_hash',
        groups=_ATTENDANCE_OFFICER,
        readonly=True,
    )
    attendance_home_pin_value = fields.Char(
        related='employee_id.attendance_home_pin_value',
        groups=_ATTENDANCE_OFFICER,
        readonly=True,
    )
    attendance_home_pin_set = fields.Boolean(
        related='employee_id.attendance_home_pin_set',
        groups=_ATTENDANCE_OFFICER,
        readonly=True,
    )
    attendance_home_pin_input = fields.Char(
        related='employee_id.attendance_home_pin_input',
        groups=_ATTENDANCE_OFFICER,
        readonly=False,
    )
    face_provider = fields.Selection(
        related='employee_id.face_provider',
        groups=_ATTENDANCE_OFFICER,
        readonly=True,
    )
    face_provider_available = fields.Boolean(
        related='employee_id.face_provider_available',
        groups=_ATTENDANCE_OFFICER,
        readonly=True,
    )
    face_attendance_stub_enabled = fields.Boolean(
        related='employee_id.face_attendance_stub_enabled',
        groups=_ATTENDANCE_OFFICER,
        readonly=True,
    )

# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.hr_attendance_custom_ext.services.face_provider_insightface import (
    haversine_distance_meters,
)


class HrEmployee(models.Model):
    _inherit = ['hr.employee', 'attendance.calendar.mixin']
    _name = 'hr.employee'

    biometric_device_user_id = fields.Char(
        string='Biometric Device User ID',
        index=True,
        groups='hr_attendance.group_hr_attendance_officer',
        help='User ID on the fingerprint device; used to map device logs to this employee.',
    )
    face_reference_id = fields.Char(
        string='Face Reference ID',
        groups='hr_attendance.group_hr_attendance_officer',
        help='Optional external face enrollment reference.',
    )
    face_template_id = fields.Char(
        string='Face Template ID',
        groups='hr_attendance.group_hr_attendance_officer',
        help='Active internal face template reference.',
    )
    face_enrollment_status = fields.Selection(
        selection=[
            ('none', 'Not Enrolled'),
            ('enrolled', 'Enrolled'),
            ('reset', 'Reset'),
        ],
        string='Face Enrollment Status',
        default='none',
        groups='hr_attendance.group_hr_attendance_officer',
    )
    face_enrolled_at = fields.Datetime(
        string='Face Enrolled At',
        groups='hr_attendance.group_hr_attendance_officer',
    )
    face_enrolled_by = fields.Many2one(
        'res.users',
        string='Face Enrolled By',
        groups='hr_attendance.group_hr_attendance_officer',
    )
    face_template_ids = fields.One2many(
        'hr.employee.face.template',
        'employee_id',
        string='Face Templates',
        groups='hr_attendance.group_hr_attendance_officer',
    )
    active_face_template_id = fields.Many2one(
        'hr.employee.face.template',
        string='Active Face Template',
        compute='_compute_active_face_template_id',
        groups='hr_attendance.group_hr_attendance_officer',
    )
    attendance_required = fields.Boolean(
        string='Attendance Required',
        default=True,
        groups='hr_attendance.group_hr_attendance_officer',
    )
    remote_attendance_allowed = fields.Boolean(
        string='Remote Face Attendance Allowed',
        default=False,
        groups='hr_attendance.group_hr_attendance_officer',
        help='Allows remote check-in/out via face verification (§9).',
    )
    face_provider = fields.Selection(
        related='company_id.face_provider',
        string='Face Provider',
        readonly=True,
        groups='hr_attendance.group_hr_attendance_officer',
    )
    face_provider_available = fields.Boolean(
        string='InsightFace Available',
        compute='_compute_face_provider_available',
        groups='hr_attendance.group_hr_attendance_officer',
    )
    face_attendance_stub_enabled = fields.Boolean(
        related='company_id.face_attendance_stub_enabled',
        string='Face Attendance Stub Enabled',
        readonly=True,
        groups='hr_attendance.group_hr_attendance_officer',
    )

    @api.depends('company_id')
    def _compute_face_provider_available(self):
        from odoo.addons.hr_attendance_custom_ext.services.face_provider_insightface import (
            InsightFaceProvider,
        )
        for employee in self:
            employee.face_provider_available = InsightFaceProvider.is_available()

    @api.depends('face_template_ids', 'face_template_ids.active')
    def _compute_active_face_template_id(self):
        Template = self.env['hr.employee.face.template']
        for employee in self:
            employee.active_face_template_id = Template.get_active_for_employee(employee)

    def write(self, vals):
        res = super().write(vals)
        if 'biometric_device_user_id' in vals:
            self._relink_fingerprint_logs()
        return res

    def _relink_fingerprint_logs(self):
        Log = self.env['fingerprint.device.log']
        for employee in self.filtered('biometric_device_user_id'):
            logs = Log.search([
                ('device_user_id', '=', employee.biometric_device_user_id),
                ('company_id', '=', employee.company_id.id),
                ('employee_id', '=', False),
                ('state', 'in', ('draft', 'error')),
            ])
            if not logs:
                continue
            logs.write({
                'employee_id': employee.id,
                'employee_name': employee.name,
            })
            logs.filtered(lambda log: log.state == 'error').write({
                'state': 'draft',
                'error_message': False,
            })

    def action_open_face_enroll_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Enroll Face Template',
            'res_model': 'hr.employee.face.enroll.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_employee_id': self.id},
        }

    def action_reset_face_enrollment(self):
        self.ensure_one()
        templates = self.face_template_ids.filtered('active')
        if templates:
            templates.write({'active': False})
        self.write({
            'face_enrollment_status': 'reset',
            'face_template_id': False,
            'face_enrolled_at': False,
            'face_enrolled_by': False,
        })
        return True

    def action_view_face_templates(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Face Templates',
            'res_model': 'hr.employee.face.template',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

    def _get_effective_work_location_type(self):
        self.ensure_one()
        try:
            return self.work_location_type or 'other'
        except Exception:
            return 'other'

    def _is_office_geo_configured(self):
        self.ensure_one()
        lat, lng, _radius = self._get_office_geo_reference()
        return bool(lat and lng)

    def _get_office_geo_reference(self):
        self.ensure_one()
        try:
            company = self.company_id
            if company.office_geo_latitude and company.office_geo_longitude:
                return (
                    company.office_geo_latitude,
                    company.office_geo_longitude,
                    company.office_geo_radius_meters or 500,
                )
            work_location = self.work_location_id
            if work_location and work_location.location_type == 'office' and work_location.address_id:
                partner = work_location.address_id
                latitude = getattr(partner, 'partner_latitude', False)
                longitude = getattr(partner, 'partner_longitude', False)
                if latitude and longitude:
                    return (
                        latitude,
                        longitude,
                        company.office_geo_radius_meters or 500,
                    )
        except Exception:
            return False, False, 0
        return False, False, 0

    def _get_attendance_systray_user_data(self):
        """Extend standard systray payload with work-location check-in rules."""
        from odoo.addons.hr_attendance.controllers.main import HrAttendance

        self.ensure_one()
        response = HrAttendance._get_user_attendance_data(self)
        location_type = self._get_effective_work_location_type()
        response.update({
            'work_location_type': location_type,
            'check_in_requires_face': location_type == 'home',
            'check_in_requires_office_geo': location_type == 'office',
            'office_geo_configured': self._is_office_geo_configured(),
        })
        return response

    def _validate_single_daily_check_in(self):
        self.ensure_one()
        policy = self.env['fingerprint.attendance.policy'].get_company_default(self.company_id)
        if policy.allow_multiple_attendances_per_day:
            return
        today = fields.Date.context_today(self)
        if self.env['hr.attendance'].search_count([
            ('employee_id', '=', self.id),
            ('date', '=', today),
        ]):
            raise UserError(_('You have already checked in today. Only one check-in per day is allowed.'))

    def _validate_office_geolocation(self, latitude, longitude, device_location=False):
        self.ensure_one()
        if not device_location:
            raise UserError(_('Your device location is required to check in from the office.'))
        if not latitude or not longitude:
            raise UserError(_('Your device location is required to check in from the office.'))

        lat_ref, lng_ref, radius = self._get_office_geo_reference()
        if not lat_ref or not lng_ref:
            raise UserError(_('Office geolocation is not configured. Please contact HR.'))

        distance = haversine_distance_meters(lat_ref, lng_ref, latitude, longitude)
        if radius and distance > radius:
            raise UserError(_(
                'You must be at the office to check in. You are %(distance).0f m away (allowed radius: %(radius)s m).',
                distance=distance,
                radius=radius,
            ))
        return distance

    def _validate_attendance_check_in(self, geo_information=None, via_face=False, device_location=False):
        self.ensure_one()
        if self.attendance_state == 'checked_in':
            return

        self._validate_single_daily_check_in()
        location_type = self._get_effective_work_location_type()

        if location_type == 'home':
            if not via_face:
                raise UserError(_('Face verification is required when working from home.'))
            return

        if location_type == 'office':
            if via_face:
                raise UserError(_('Office check-in requires geolocation. Use the attendance menu instead.'))
            latitude = geo_information.get('latitude') if geo_information else False
            longitude = geo_information.get('longitude') if geo_information else False
            self._validate_office_geolocation(latitude, longitude, device_location=device_location)

    def _attendance_action_change(self, geo_information=None):
        self._validate_attendance_check_in(
            geo_information,
            via_face=self.env.context.get('attendance_via_face'),
            device_location=self.env.context.get('attendance_device_location'),
        )
        attendance = super()._attendance_action_change(geo_information=geo_information)
        if attendance and not attendance.attendance_source:
            mode_map = {
                'kiosk': 'kiosk',
                'systray': 'systray',
            }
            if self.attendance_state == 'checked_in':
                source = mode_map.get(attendance.in_mode, 'manual')
            else:
                source = mode_map.get(attendance.out_mode, 'manual')
            attendance.attendance_source = source
        return attendance

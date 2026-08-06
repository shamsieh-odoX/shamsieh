# -*- coding: utf-8 -*-

import binascii
import hashlib
import hmac
import logging
import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.hr_attendance_custom_ext.services.face_provider_insightface import (
    haversine_distance_meters,
)

_logger = logging.getLogger(__name__)

# Primary mapping order for Hikvision / fingerprint device_user_id.
_DEVICE_USER_ID_LOOKUP_FIELDS = (
    'biometric_device_user_id',
    'barcode',  # standard hr: labeled "Badge ID" (RFID/Badge Number)
    'shams_employee_code',
    'identification_id',
    'pin',
)
# Extra RFID/badge fields from custom modules (skipped if missing).
_RFID_BADGE_FIELD_CANDIDATES = (
    'rfid',
    'rfid_code',
    'badge_id',
    'badge_number',
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
    hikvision_presence_status = fields.Selection(
        selection=[
            ('checked_out', 'Checked Out'),
            ('working', 'Working'),
            ('on_break', 'On Break'),
        ],
        string='Hikvision Presence',
        default='checked_out',
        index=True,
        help='Live work state from Hikvision / Odoo punches. '
             'Break Out starts a break; Break In ends a break.',
    )
    live_check_in = fields.Datetime(
        string='Checked In At',
        compute='_compute_live_break_info',
        help='Check-in time of the current open attendance.',
    )
    current_break_start = fields.Datetime(
        string='Break Started',
        compute='_compute_live_break_info',
        help='Start of the current open break, or the most recent break start.',
    )
    current_break_hours = fields.Float(
        string='Total Break Time',
        compute='_compute_live_break_info',
        help='Total time on break for the current open attendance. '
             'Completed breaks are summed; an open break keeps counting.',
    )
    break_count = fields.Integer(
        string='Breaks',
        compute='_compute_live_break_info',
        help='How many times the employee started a break on the current open attendance.',
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
    attendance_face_image_preview = fields.Binary(
        string='Enrolled Face Image',
        compute='_compute_attendance_face_image_preview',
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
    attendance_home_pin_hash = fields.Char(
        string='Home Attendance PIN Hash',
        groups='hr_attendance.group_hr_attendance_officer',
        copy=False,
    )
    attendance_home_pin_value = fields.Char(
        string='Home Attendance PIN',
        groups='hr_attendance.group_hr_attendance_officer',
        copy=False,
        help='Displayed PIN value configured for home attendance.',
    )
    attendance_home_pin_set = fields.Boolean(
        string='Home Attendance PIN Set',
        compute='_compute_attendance_home_pin_set',
        groups='hr_attendance.group_hr_attendance_officer',
    )
    attendance_home_pin_input = fields.Char(
        string='Home PIN',
        compute='_compute_attendance_home_pin_input',
        inverse='_inverse_attendance_home_pin_input',
        groups='hr_attendance.group_hr_attendance_officer',
        copy=False,
        help='Home attendance PIN. Leave unchanged on save to keep the current value.',
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

    @api.depends('hikvision_presence_status')
    def _compute_live_break_info(self):
        """Live board: open check-in, break start, total break time, and break count."""
        Attendance = self.env['hr.attendance'].sudo()
        PunchLog = self.env['hr.attendance.punch.log'].sudo()
        now = fields.Datetime.now()

        for employee in self:
            employee.live_check_in = False
            employee.current_break_start = False
            employee.current_break_hours = 0.0
            employee.break_count = 0

        if not self:
            return

        open_attendances = Attendance.search([
            ('employee_id', 'in', self.ids),
            ('check_out', '=', False),
        ], order='check_in desc')
        open_by_employee = {}
        for attendance in open_attendances:
            if attendance.employee_id.id not in open_by_employee:
                open_by_employee[attendance.employee_id.id] = attendance

        attendance_ids = [att.id for att in open_by_employee.values()]
        punches_by_attendance = {att_id: [] for att_id in attendance_ids}
        if attendance_ids:
            punches = PunchLog.search([
                ('attendance_id', 'in', attendance_ids),
                ('punch_type', 'in', ('break_out', 'break_in')),
            ], order='punch_time asc, id asc')
            for punch in punches:
                punches_by_attendance.setdefault(punch.attendance_id.id, []).append(punch)

        for employee in self:
            attendance = open_by_employee.get(employee.id)
            if not attendance:
                continue
            employee.live_check_in = attendance.check_in

            open_start = None
            last_start = None
            total_seconds = 0.0
            break_count = 0
            for punch in punches_by_attendance.get(attendance.id, []):
                if punch.punch_type == 'break_out':
                    if open_start:
                        # Consecutive Break Out: close the previous open break here.
                        total_seconds += (punch.punch_time - open_start).total_seconds()
                    open_start = punch.punch_time
                    last_start = punch.punch_time
                    break_count += 1
                elif punch.punch_type == 'break_in' and open_start:
                    total_seconds += (punch.punch_time - open_start).total_seconds()
                    open_start = None

            if open_start:
                total_seconds += (now - open_start).total_seconds()
                employee.current_break_start = open_start
            else:
                employee.current_break_start = last_start

            employee.current_break_hours = max(total_seconds, 0.0) / 3600.0
            employee.break_count = break_count

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

    @api.depends('face_template_ids', 'face_template_ids.active', 'face_template_ids.image_attachment_id')
    def _compute_attendance_face_image_preview(self):
        Template = self.env['hr.employee.face.template']
        for employee in self:
            template = Template.get_active_for_employee(employee)
            employee.attendance_face_image_preview = (
                template.image_attachment_id.datas if template and template.image_attachment_id else False
            )

    @api.depends('attendance_home_pin_hash')
    def _compute_attendance_home_pin_set(self):
        for employee in self:
            employee.attendance_home_pin_set = bool(employee.attendance_home_pin_hash)

    @api.depends('attendance_home_pin_value')
    def _compute_attendance_home_pin_input(self):
        for employee in self:
            employee.attendance_home_pin_input = employee.attendance_home_pin_value or False

    def _inverse_attendance_home_pin_input(self):
        for employee in self:
            new_value = employee.attendance_home_pin_input
            current_value = employee.attendance_home_pin_value or ''
            if new_value == current_value:
                continue
            if not employee._normalize_attendance_pin(new_value):
                employee.attendance_home_pin_input = current_value or False
                continue
            employee._set_home_attendance_pin(new_value)

    def write(self, vals):
        res = super().write(vals)
        if 'biometric_device_user_id' in vals:
            self._relink_fingerprint_logs()
        return res

    def _normalize_attendance_pin(self, pin_code):
        self.ensure_one()
        return (pin_code or '').strip()

    def _build_attendance_pin_hash(self, pin_code):
        normalized = self._normalize_attendance_pin(pin_code)
        if not normalized:
            raise UserError(_('PIN cannot be empty.'))
        if not normalized.isdigit():
            raise UserError(_('PIN must contain digits only.'))
        if len(normalized) < 4:
            raise UserError(_('PIN must be at least 4 digits.'))
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac('sha256', normalized.encode(), salt, 120000)
        return '%s$%s' % (
            binascii.hexlify(salt).decode(),
            binascii.hexlify(digest).decode(),
        )

    def _set_home_attendance_pin(self, pin_code):
        for employee in self:
            normalized = employee._normalize_attendance_pin(pin_code)
            if not normalized:
                employee.attendance_home_pin_hash = False
                employee.attendance_home_pin_value = False
                continue
            employee.attendance_home_pin_hash = employee._build_attendance_pin_hash(normalized)
            employee.attendance_home_pin_value = normalized

    def _verify_home_attendance_pin(self, pin_code):
        self.ensure_one()
        normalized = self._normalize_attendance_pin(pin_code)
        stored = self.attendance_home_pin_hash or ''
        if not normalized or '$' not in stored:
            return False
        salt_hex, digest_hex = stored.split('$', 1)
        if not salt_hex or not digest_hex:
            return False
        try:
            salt = binascii.unhexlify(salt_hex.encode())
            expected = binascii.unhexlify(digest_hex.encode())
        except (binascii.Error, ValueError):
            return False
        calculated = hashlib.pbkdf2_hmac('sha256', normalized.encode(), salt, 120000)
        return hmac.compare_digest(expected, calculated)

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

    @api.model
    def _normalize_device_user_id(self, value):
        if value in (False, None):
            return ''
        return str(value).strip()

    @api.model
    def _device_user_id_lookup_fields(self):
        """Ordered employee fields used to match a device user id."""
        field_names = [
            name for name in _DEVICE_USER_ID_LOOKUP_FIELDS
            if name in self._fields
        ]
        for name in _RFID_BADGE_FIELD_CANDIDATES:
            if name in self._fields and name not in field_names:
                field_names.append(name)
        return field_names

    @api.model
    def resolve_by_device_user_id(self, device_user_id, company):
        """Match device_user_id to one employee.

        Returns ``(employee_recordset, matched_field_name_or_False)``.
        Comparison is stringified and stripped on both sides.
        """
        needle = self._normalize_device_user_id(device_user_id)
        company_id = company.id if getattr(company, 'id', None) else company
        if not needle or not company_id:
            return self.browse(), False

        lookup_fields = self._device_user_id_lookup_fields()
        _logger.info(
            'Hikvision mapping lookup: device_user_id=%r company_id=%s fields=%s',
            needle,
            company_id,
            lookup_fields,
        )

        employees = self.search([('company_id', '=', company_id)])
        for field_name in lookup_fields:
            matches = employees.filtered(
                lambda emp, fname=field_name: (
                    self._normalize_device_user_id(emp[fname]) == needle
                ),
            )
            if not matches:
                continue
            if len(matches) > 1:
                _logger.warning(
                    'Hikvision mapping: device_user_id=%r matched %s employees '
                    'via %s; using employee_id=%s',
                    needle,
                    len(matches),
                    field_name,
                    matches[0].id,
                )
            employee = matches[0]
            _logger.info(
                'Hikvision mapping matched: device_user_id=%r employee_id=%s '
                'employee_name=%r field=%s',
                needle,
                employee.id,
                employee.name,
                field_name,
            )
            return employee, field_name

        candidates = []
        for emp in employees:
            row = {
                'id': emp.id,
                'name': emp.name,
            }
            for field_name in lookup_fields:
                row[field_name] = self._normalize_device_user_id(emp[field_name])
            candidates.append(row)
        _logger.info(
            'Hikvision mapping no match for device_user_id=%r. Candidates: %s',
            needle,
            candidates,
        )
        return self.browse(), False

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

    def action_clear_home_attendance_pin(self):
        self.write({
            'attendance_home_pin_hash': False,
            'attendance_home_pin_value': False,
        })
        return True

    def _get_attendance_scheduled_location(self, check_datetime=None):
        """Schedule-only location for attendance rules. Defaults to office."""
        self.ensure_one()
        location = self._get_schedule_location_type(
            check_datetime=check_datetime or fields.Datetime.now(),
        )
        if location == 'home':
            return 'home'
        return 'office'

    def _manual_attendance_allowed(self, check_datetime=None):
        self.ensure_one()
        return self._get_attendance_scheduled_location(check_datetime) == 'home'

    def _systray_break_punch_allowed(self, check_datetime=None):
        """Allow Break Out / Break In from Odoo for all employees (office and home).

        Fingerprint/Hikvision break punches are always accepted separately when the
        device sends attendanceStatus breakOut/breakIn.
        """
        self.ensure_one()
        return True

    def _raise_if_manual_attendance_blocked(self, check_datetime=None):
        self.ensure_one()
        if not self._manual_attendance_allowed(check_datetime):
            raise UserError(_(
                'Manual attendance is not allowed on office schedule days. '
                'Please use the fingerprint device to check in and out.'
            ))

    def _raise_if_systray_break_blocked(self, check_datetime=None):
        self.ensure_one()
        if not self._systray_break_punch_allowed(check_datetime):
            raise UserError(_(
                'Break punches from Odoo are currently not allowed.'
            ))

    def _get_effective_work_location_type(self):
        self.ensure_one()
        schedule_location = self._get_schedule_location_type()
        if schedule_location:
            return schedule_location
        work_location = self.work_location_id
        if work_location and work_location.location_type:
            return work_location.location_type
        return self.work_location_type or 'other'

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

    def _hikvision_any_attendance_today(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        return bool(self.env['hr.attendance'].sudo().search_count([
            ('employee_id', '=', self.id),
            ('date', '=', today),
        ]))

    def _get_tz(self):
        """Prefer a real local timezone over UTC for attendance lateness.

        Working hours (e.g. 08:00-16:00) are business-local. If the calendar is
        still set to UTC, fall back to the employee/user/company Asia/Amman zone.
        """
        self.ensure_one()
        candidates = [
            self.tz,
            self.resource_id.tz if self.resource_id else False,
            self.resource_calendar_id.tz if self.resource_calendar_id else False,
            self.company_id.resource_calendar_id.tz if self.company_id.resource_calendar_id else False,
            self.env.user.tz,
            'Asia/Amman',
        ]
        for tz_name in candidates:
            if tz_name and tz_name != 'UTC':
                return tz_name
        return 'Asia/Amman'

    def _sync_hikvision_presence_from_last_punch(self):
        """Align work state with the latest punch (Break Out=on break, Break In=working)."""
        PunchLog = self.env['hr.attendance.punch.log'].sudo()
        Attendance = self.env['hr.attendance'].sudo()
        for employee in self:
            open_attendance = Attendance.search([
                ('employee_id', '=', employee.id),
                ('check_out', '=', False),
            ], order='check_in desc', limit=1)
            if not open_attendance:
                if employee.hikvision_presence_status != 'checked_out':
                    employee.sudo().hikvision_presence_status = 'checked_out'
                continue
            last_punch = PunchLog.search([
                ('attendance_id', '=', open_attendance.id),
            ], order='punch_time desc, id desc', limit=1)
            punch_type = last_punch.punch_type if last_punch else open_attendance.hikvision_punch_type
            if punch_type == 'break_out':
                status = 'on_break'
            elif punch_type in ('check_in', 'break_in'):
                status = 'working'
            elif punch_type == 'check_out':
                status = 'checked_out'
            else:
                status = 'working'
            if employee.hikvision_presence_status != status:
                employee.sudo().hikvision_presence_status = status
            if punch_type and open_attendance.hikvision_punch_type != punch_type:
                open_attendance.hikvision_punch_type = punch_type

    def hikvision_process_punch(
        self,
        punch_type,
        punch_time,
        external_log_id=False,
        device_user_id=False,
        attendance_source='fingerprint',
    ):
        """Process a Hikvision punch without treating breaks as checkout."""
        self.ensure_one()
        Attendance = self.env['hr.attendance'].sudo()
        PunchLog = self.env['hr.attendance.punch.log'].sudo()
        open_attendance = Attendance.search([
            ('employee_id', '=', self.id),
            ('check_out', '=', False),
        ], order='check_in desc', limit=1)

        if external_log_id:
            duplicate = PunchLog.search([
                ('external_log_id', '=', external_log_id),
                ('employee_id', '=', self.id),
            ], limit=1)
            if duplicate:
                return {
                    'status': 'duplicate',
                    'attendance_id': duplicate.attendance_id.id,
                }

        source_vals = {
            'attendance_source': attendance_source,
            'device_user_id': device_user_id,
            'external_log_id': external_log_id,
        }
        source_vals = {key: value for key, value in source_vals.items() if value}

        if punch_type == 'check_in':
            if open_attendance:
                return {'status': 'duplicate', 'attendance_id': open_attendance.id}
            policy = self.env['fingerprint.attendance.policy'].get_company_default(self.company_id)
            if not policy.allow_multiple_attendances_per_day and self._hikvision_any_attendance_today():
                today_attendance = Attendance.search([
                    ('employee_id', '=', self.id),
                    ('date', '=', fields.Date.context_today(self)),
                ], order='check_in desc', limit=1)
                return {
                    'status': 'duplicate',
                    'attendance_id': today_attendance.id if today_attendance else False,
                    'reason': 'already_checked_in_today',
                }
            attendance = Attendance.create({
                'employee_id': self.id,
                'check_in': punch_time,
                'hikvision_punch_type': punch_type,
                'in_mode': 'technical',
                **source_vals,
            })
            self.sudo().hikvision_presence_status = 'working'
            PunchLog.create({
                'attendance_id': attendance.id,
                'punch_type': punch_type,
                'punch_time': punch_time,
                'attendance_source': attendance_source,
                'device_user_id': device_user_id,
                'external_log_id': external_log_id,
            })
            return {'status': 'created', 'attendance_id': attendance.id}

        if punch_type == 'check_out':
            if not open_attendance:
                return {'status': 'no_open_attendance'}
            open_attendance.write({
                'check_out': punch_time,
                'hikvision_punch_type': punch_type,
                'out_mode': 'technical',
                **source_vals,
            })
            PunchLog.create({
                'attendance_id': open_attendance.id,
                'punch_type': punch_type,
                'punch_time': punch_time,
                'attendance_source': attendance_source,
                'device_user_id': device_user_id,
                'external_log_id': external_log_id,
            })
            self.sudo().hikvision_presence_status = 'checked_out'
            return {'status': 'closed', 'attendance_id': open_attendance.id}

        if punch_type == 'break_out':
            # Break Out = leave for break (break started)
            if not open_attendance:
                return {'status': 'no_open_attendance'}
            if self.hikvision_presence_status == 'on_break':
                return {'status': 'duplicate', 'attendance_id': open_attendance.id}
            self.sudo().hikvision_presence_status = 'on_break'
            open_attendance.write({'hikvision_punch_type': punch_type})
            PunchLog.create({
                'attendance_id': open_attendance.id,
                'punch_type': punch_type,
                'punch_time': punch_time,
                'attendance_source': attendance_source,
                'device_user_id': device_user_id,
                'external_log_id': external_log_id,
            })
            return {'status': 'break_started', 'attendance_id': open_attendance.id}

        if punch_type == 'break_in':
            # Break In = return from break (break ended)
            if not open_attendance:
                return {'status': 'no_open_attendance'}
            on_break = self.hikvision_presence_status == 'on_break'
            if not on_break:
                last_punch = PunchLog.search([
                    ('attendance_id', '=', open_attendance.id),
                ], order='punch_time desc, id desc', limit=1)
                if not last_punch or last_punch.punch_type != 'break_out':
                    return {'status': 'not_on_break', 'attendance_id': open_attendance.id}
            self.sudo().hikvision_presence_status = 'working'
            open_attendance.write({'hikvision_punch_type': punch_type})
            PunchLog.create({
                'attendance_id': open_attendance.id,
                'punch_type': punch_type,
                'punch_time': punch_time,
                'attendance_source': attendance_source,
                'device_user_id': device_user_id,
                'external_log_id': external_log_id,
            })
            return {'status': 'break_ended', 'attendance_id': open_attendance.id}

        return {'status': 'ignored', 'punch_type': punch_type}

    @api.model
    def hikvision_bridge_punch(
        self,
        employee_id,
        punch_type,
        punch_time,
        external_log_id=False,
        device_user_id=False,
        attendance_source='fingerprint',
    ):
        """XML-RPC entry point for the local Hikvision bridge."""
        employee = self.browse(int(employee_id)).exists()
        if not employee:
            return {'status': 'employee_not_found', 'employee_id': employee_id}
        return employee.hikvision_process_punch(
            punch_type=punch_type,
            punch_time=punch_time,
            external_log_id=external_log_id,
            device_user_id=device_user_id,
            attendance_source=attendance_source,
        )

    def action_systray_punch(self, punch_type):
        self.ensure_one()
        if punch_type in ('break_in', 'break_out'):
            self._raise_if_systray_break_blocked()
        else:
            self._raise_if_manual_attendance_blocked()
        return self.with_context(attendance_employee_self_punch=True).hikvision_process_punch(
            punch_type=punch_type,
            punch_time=fields.Datetime.now(),
            attendance_source='systray',
        )

    def _get_attendance_systray_user_data(self):
        """Extend standard systray payload with work-location check-in rules."""
        from odoo.addons.hr_attendance.controllers.main import HrAttendance

        self.ensure_one()
        response = HrAttendance._get_user_attendance_data(self)
        scheduled_location = self._get_attendance_scheduled_location()
        manual_allowed = scheduled_location == 'home'
        break_allowed = self._systray_break_punch_allowed()
        policy = self.env['fingerprint.attendance.policy'].get_company_default(self.company_id)
        response.update({
            'scheduled_location': scheduled_location,
            'manual_attendance_allowed': manual_allowed,
            'break_punch_allowed': break_allowed,
            'work_location_type': scheduled_location,
            'check_in_requires_face': False,
            'check_in_requires_home_pin': False,
            'check_in_requires_office_geo': False,
            'office_geo_configured': self._is_office_geo_configured(),
            'single_check_in_per_day': not policy.allow_multiple_attendances_per_day,
            'hikvision_presence_status': self.hikvision_presence_status or 'checked_out',
        })
        return response

    def _validate_single_daily_check_in(self):
        self.ensure_one()
        policy = self.env['fingerprint.attendance.policy'].get_company_default(self.company_id)
        if policy.allow_multiple_attendances_per_day:
            return
        if self.attendance_state == 'checked_in':
            raise UserError(_('You are already checked in.'))
        today = fields.Date.context_today(self)
        if self.env['hr.attendance'].search_count([
            ('employee_id', '=', self.id),
            ('date', '=', today),
            ('check_out', '=', False),
        ]):
            raise UserError(_('You are already checked in.'))
        if self.env['hr.attendance'].search_count([
            ('employee_id', '=', self.id),
            ('date', '=', today),
            ('check_out', '!=', False),
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

    def _validate_attendance_check_in(
        self,
        geo_information=None,
        via_face=False,
        via_home_pin=False,
        device_location=False,
    ):
        self.ensure_one()
        if self.attendance_state == 'checked_in':
            return

        self._raise_if_manual_attendance_blocked()
        self._validate_single_daily_check_in()

    def _attendance_action_change(self, geo_information=None):
        self._raise_if_manual_attendance_blocked()
        if self.attendance_state != 'checked_in':
            self._validate_attendance_check_in(
                geo_information,
                via_face=self.env.context.get('attendance_via_face'),
                via_home_pin=self.env.context.get('attendance_via_home_pin'),
                device_location=self.env.context.get('attendance_device_location'),
            )
        attendance = super(
            type(self), self.with_context(attendance_employee_self_punch=True)
        )._attendance_action_change(geo_information=geo_information)
        if attendance and not attendance.attendance_source:
            mode_map = {
                'kiosk': 'kiosk',
                'systray': 'systray',
            }
            if self.attendance_state == 'checked_in':
                source = mode_map.get(attendance.in_mode, 'manual')
            else:
                source = mode_map.get(attendance.out_mode, 'manual')
            attendance.with_context(attendance_employee_self_punch=True).attendance_source = source
        return attendance

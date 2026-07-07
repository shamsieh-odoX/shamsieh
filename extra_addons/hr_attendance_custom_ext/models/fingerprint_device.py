# -*- coding: utf-8 -*-

import logging
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..services.hikvision_connector import HikvisionConnector

_logger = logging.getLogger(__name__)


class FingerprintDevice(models.Model):
    _name = 'fingerprint.device'
    _description = 'Fingerprint Device'
    _order = 'name'

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    policy_id = fields.Many2one(
        'fingerprint.attendance.policy',
        string='Attendance Policy',
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
    )
    device_ip = fields.Char(string='Device IP')
    device_port = fields.Integer(string='Port', default=80)
    api_type = fields.Selection(
        selection=[
            ('hikvision', 'Hikvision ISAPI'),
            ('zkteco', 'ZKTeco'),
            ('file_import', 'File Import (CSV)'),
            ('custom_api', 'Custom API'),
        ],
        string='API Type',
        default='hikvision',
        required=True,
    )
    username = fields.Char(groups='hr_attendance_custom_ext.group_fingerprint_device_manager')
    password = fields.Char(groups='hr_attendance_custom_ext.group_fingerprint_device_manager')
    api_key = fields.Char(groups='hr_attendance_custom_ext.group_fingerprint_device_manager')
    sync_lookback_hours = fields.Float(
        string='Sync Lookback (hours)',
        default=24.0,
        help='How many hours back to fetch access events on each sync.',
    )
    device_timezone = fields.Char(
        string='Device Timezone',
        help='IANA timezone of the device clock (e.g. Asia/Amman). '
             'Leave empty to use the company working-hours calendar timezone.',
    )
    store_ignored_events = fields.Boolean(
        string='Store All Device Events',
        default=False,
        help='When enabled, door/system events are saved with state Ignored. '
             'When disabled, only attendance-relevant authentication events are stored.',
    )
    sync_status = fields.Selection(
        selection=[
            ('idle', 'Idle'),
            ('running', 'Running'),
            ('success', 'Success'),
            ('error', 'Error'),
        ],
        default='idle',
        readonly=True,
    )
    connection_timeout = fields.Integer(string='Connection Timeout (s)', default=15)
    sync_retry_count = fields.Integer(string='Sync Retries', default=2)
    last_sync_checkpoint = fields.Datetime(
        string='Last Sync Checkpoint',
        readonly=True,
        help='Narrow event fetch window after successful sync.',
    )
    last_successful_event_serial = fields.Char(readonly=True)
    last_sync_at = fields.Datetime(readonly=True)
    last_sync_message = fields.Text(readonly=True)
    active = fields.Boolean(default=True)
    auto_sync = fields.Boolean(string='Auto Sync', default=True)
    sync_interval_minutes = fields.Float(
        string='Polling Fallback Interval (minutes)',
        default=15.0,
        help='When HTTP listening is active and receiving events, polling is skipped. '
             'If no push is received within this window, the scheduler fetches events '
             'from the device as a backup.',
    )
    import_file_data = fields.Binary(
        string='Import File',
        attachment=True,
        help='CSV for file_import API type: external_id,device_user_id,punch_time,punch_type',
    )
    import_file_name = fields.Char()
    log_ids = fields.One2many('fingerprint.device.log', 'device_id', string='Sync Logs')
    log_count = fields.Integer(compute='_compute_log_counts')
    draft_log_count = fields.Integer(compute='_compute_log_counts')
    error_log_count = fields.Integer(compute='_compute_log_counts')
    processed_log_count = fields.Integer(compute='_compute_log_counts')
    http_listening_enabled = fields.Boolean(
        string='HTTP Listening',
        default=True,
        help='When enabled, the device pushes access events to Odoo in real time. '
             'Scheduled polling is used only as a fallback when pushes stop.',
    )
    http_listening_token = fields.Char(
        string='HTTP Listening Token',
        copy=False,
        groups='hr_attendance_custom_ext.group_fingerprint_device_manager',
    )
    http_listening_allowed_ips = fields.Char(
        string='Allowed Source IPs',
        help='Comma-separated IPs allowed to POST events (defaults to device IP when enabled).',
        groups='hr_attendance_custom_ext.group_fingerprint_device_manager',
    )
    http_listening_last_at = fields.Datetime(
        string='Last HTTP Push',
        readonly=True,
    )
    http_listening_url = fields.Char(
        string='Callback URL',
        compute='_compute_http_listening_url',
    )

    _http_listening_token_uniq = models.Constraint(
        'unique(http_listening_token)',
        'HTTP listening token must be unique.',
    )

    @api.depends('http_listening_token')
    def _compute_http_listening_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', '',
        ).rstrip('/')
        for device in self:
            if device.http_listening_token and base_url:
                device.http_listening_url = (
                    f'{base_url}/hikvision/event/{device.http_listening_token}'
                )
            else:
                device.http_listening_url = False

    @api.model
    def _generate_http_listening_token(self):
        return secrets.token_urlsafe(32)

    def _is_ip_allowed(self, remote_ip):
        self.ensure_one()
        if not remote_ip:
            return False
        allowed = [
            ip.strip()
            for ip in (self.http_listening_allowed_ips or '').split(',')
            if ip.strip()
        ]
        if not allowed and self.device_ip:
            allowed = [self.device_ip.strip()]
        if not allowed:
            return False
        return remote_ip.strip() in allowed

    @api.model
    def _find_http_listening_device(self, token):
        if not token:
            return self.browse()
        return self.sudo().search([
            ('http_listening_enabled', '=', True),
            ('http_listening_token', '=', token),
            ('active', '=', True),
            ('api_type', '=', 'hikvision'),
        ], limit=1)

    def action_regenerate_http_listening_token(self):
        self.ensure_one()
        self.write({'http_listening_token': self._generate_http_listening_token()})
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('http_listening_enabled'):
                if not vals.get('http_listening_token'):
                    vals['http_listening_token'] = self._generate_http_listening_token()
                if not vals.get('http_listening_allowed_ips') and vals.get('device_ip'):
                    vals['http_listening_allowed_ips'] = vals['device_ip']
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if vals.get('http_listening_enabled'):
            for device in self.filtered('http_listening_enabled'):
                patch = {}
                if not device.http_listening_token:
                    patch['http_listening_token'] = device._generate_http_listening_token()
                if not device.http_listening_allowed_ips and device.device_ip:
                    patch['http_listening_allowed_ips'] = device.device_ip
                if patch:
                    super(FingerprintDevice, device).write(patch)
        return res

    @api.constrains('http_listening_token')
    def _check_http_listening_token(self):
        for device in self:
            if device.http_listening_token and len(device.http_listening_token) < 16:
                raise ValidationError(_('HTTP listening token must be at least 16 characters.'))

    @api.depends('log_ids', 'log_ids.state')
    def _compute_log_counts(self):
        for device in self:
            device.log_count = len(device.log_ids)
            device.draft_log_count = len(device.log_ids.filtered(lambda log: log.state == 'draft'))
            device.error_log_count = len(device.log_ids.filtered(lambda log: log.state == 'error'))
            device.processed_log_count = len(device.log_ids.filtered(lambda log: log.state == 'processed'))

    def _get_attendance_policy(self):
        self.ensure_one()
        if self.policy_id:
            return self.policy_id
        return self.env['fingerprint.attendance.policy'].get_company_default(self.company_id)

    def _auto_sync_device(self):
        """Fetch device events, remap employees, and process attendance (used by cron)."""
        self.ensure_one()
        self._sync_device()
        self._process_pending_drafts()

    def _process_pending_drafts(self):
        """Remap employees and process draft attendance logs without fetching from device."""
        self.ensure_one()
        self._refresh_log_employee_mappings()
        errors = self.log_ids.filtered(lambda log: log.state == 'error' and log.device_user_id)
        for log in errors:
            if log._resolve_employee():
                log.write({'state': 'draft', 'error_message': False})
        self.log_ids.filtered(lambda log: log.state == 'draft')._process_pending_logs()

    def _http_listening_is_live(self, now=None):
        """Return True when recent HTTP pushes indicate live sync is healthy."""
        self.ensure_one()
        if not self.http_listening_enabled or not self.http_listening_last_at:
            return False
        now = now or fields.Datetime.now()
        fallback = timedelta(minutes=self.sync_interval_minutes or 15.0)
        return (now - self.http_listening_last_at) < fallback

    def _action_view_logs_domain(self, extra_domain=None):
        self.ensure_one()
        domain = [('device_id', '=', self.id)]
        if extra_domain:
            domain += extra_domain
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fingerprint Sync Logs'),
            'res_model': 'fingerprint.device.log',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'default_device_id': self.id},
            'limit': 200,
        }

    def action_view_logs(self):
        return self._action_view_logs_domain()

    def _refresh_log_employee_mappings(self):
        """Link draft/error logs to employees when biometric IDs were configured later."""
        self.ensure_one()
        Log = self.env['fingerprint.device.log']
        candidates = Log.search([
            ('device_id', '=', self.id),
            ('employee_id', '=', False),
            ('device_user_id', '!=', False),
            ('state', 'in', ('draft', 'error')),
        ])
        for log in candidates:
            employee = log._resolve_employee()
            if employee and log.state == 'error':
                log.write({'state': 'draft', 'error_message': False})

    def _notify_hr_managers(self, summary, note):
        self.ensure_one()
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return
        group = self.env.ref('hr_attendance.group_hr_attendance_manager', raise_if_not_found=False)
        users = group.user_ids.filtered(lambda u: self.company_id in u.company_ids) if group else self.env.user
        Activity = self.env['mail.activity']
        model_id = self.env['ir.model']._get('fingerprint.device').id
        for user in users:
            Activity.create({
                'activity_type_id': activity_type.id,
                'summary': summary,
                'note': note,
                'res_model_id': model_id,
                'res_id': self.id,
                'user_id': user.id,
            })

    def _notify_sync_issues(self, logs, stats):
        self.ensure_one()
        if stats.get('unmapped'):
            unmapped = logs.filtered(lambda log: log.state == 'draft' and not log.employee_id)
            if unmapped:
                self._notify_hr_managers(
                    _('Unmapped fingerprint events'),
                    _('%(count)s event(s) have no employee mapping on device %(device)s.',
                      count=len(unmapped), device=self.name),
                )

    def _sync_device(self):
        self.ensure_one()
        self.sync_status = 'running'
        try:
            connector = HikvisionConnector(self)
            logs, stats = connector.sync_device_logs()
            self.write({
                'sync_status': 'success',
                'last_sync_at': fields.Datetime.now(),
                'last_sync_message': _(
                    'Fetched %(fetched)s | stored %(stored)s | ignored %(ignored)s | '
                    'duplicates %(duplicates)s | unmapped %(unmapped)s | skipped %(skipped)s',
                    **stats,
                ),
            })
            self._notify_sync_issues(logs, stats)
            return logs
        except Exception as exc:
            self.write({
                'sync_status': 'error',
                'last_sync_at': fields.Datetime.now(),
                'last_sync_message': str(exc),
            })
            try:
                self._notify_hr_managers(
                    _('Fingerprint device sync failed'),
                    _('Device %(device)s: %(error)s', device=self.name, error=str(exc)),
                )
            except Exception:
                _logger.exception('Failed to notify HR managers about sync failure for %s', self.name)
            raise UserError(_('Sync failed: %s', exc)) from exc

    @api.model
    def _cron_sync_all(self):
        now = fields.Datetime.now()
        devices = self.search([('active', '=', True), ('auto_sync', '=', True)])
        for device in devices:
            if device._http_listening_is_live(now):
                try:
                    device._process_pending_drafts()
                except UserError as exc:
                    _logger.warning(
                        'Fingerprint draft processing failed for %s: %s',
                        device.name, exc,
                    )
                continue
            interval = device.sync_interval_minutes or 15.0
            if device.last_sync_at and (now - device.last_sync_at) < timedelta(minutes=interval):
                continue
            try:
                device._auto_sync_device()
            except UserError as exc:
                _logger.warning('Fingerprint auto-sync failed for %s: %s', device.name, exc)

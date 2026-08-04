# -*- coding: utf-8 -*-

import logging
import secrets
from datetime import timedelta

import psycopg2
from psycopg2 import errorcodes

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..services.zkteco_connector import get_device_connector

_logger = logging.getLogger(__name__)

HTTP_LISTENING_TOUCH_THROTTLE_SECONDS = 30
HTTP_LISTENING_KEEPALIVE_THROTTLE_SECONDS = 60


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
    password = fields.Char(
        groups='hr_attendance_custom_ext.group_fingerprint_device_manager',
        help='Hikvision password, or ZKTeco numeric communication password (Comm Key).',
    )
    api_key = fields.Char(groups='hr_attendance_custom_ext.group_fingerprint_device_manager')
    zkteco_force_udp = fields.Boolean(
        string='ZKTeco Force UDP',
        default=False,
        help='Some ZKTeco terminals require UDP instead of TCP. Enable if TCP connect fails.',
        groups='hr_attendance_custom_ext.group_fingerprint_device_manager',
    )
    zkteco_serial_number = fields.Char(
        string='ZKTeco Serial Number (SN)',
        copy=False,
        index=True,
        help='Device serial from the terminal / Attendance Management (e.g. SRN5244400238). '
             'Required for ADMS push matching.',
        groups='hr_attendance_custom_ext.group_fingerprint_device_manager',
    )
    zkteco_adms_enabled = fields.Boolean(
        string='ADMS / Cloud Push',
        default=True,
        help='Accept live attendance pushes from the ZKTeco device (iclock/ADMS), '
             'same idea as Hikvision HTTP Listening. Prefer this over Sync Now on Odoo.sh.',
    )
    zkteco_adms_url = fields.Char(
        string='ADMS Server URL',
        compute='_compute_zkteco_adms_url',
        help='Set this as Cloud Server / ADMS URL on the device (must end with /iclock/). '
             'If the terminal only supports HTTP, run the local ADMS bridge and use its URL.',
    )
    location_label = fields.Char(
        string='Office / Branch Label',
        help='Optional label for this device location (e.g. Branch B, Warehouse). '
             'Devices are scoped by company; use separate devices per physical office.',
    )
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
    auto_sync = fields.Boolean(
        string='Auto Sync',
        default=True,
        help='Poll the device over the network on a schedule. '
             'Disable this when using HTTP Listening push only (required on Odoo.sh '
             'because the cloud cannot reach LAN device IPs).',
    )
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

    @api.depends('api_type')
    def _compute_zkteco_adms_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', '',
        ).rstrip('/')
        for device in self:
            if device.api_type == 'zkteco' and base_url:
                device.zkteco_adms_url = f'{base_url}/iclock/'
            else:
                device.zkteco_adms_url = False

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
    def _is_pg_concurrency_error(self, exc):
        if isinstance(exc, psycopg2.errors.SerializationFailure):
            return True
        pgcode = getattr(exc, 'pgcode', None)
        if pgcode in (errorcodes.SERIALIZATION_FAILURE, errorcodes.DEADLOCK_DETECTED):
            return True
        message = str(exc).lower()
        return (
            'could not serialize access' in message
            or 'concurrent update' in message
        )

    def _touch_http_listening_last_at(self, force=False, throttle_seconds=None):
        """Update Last HTTP Push, throttled to avoid concurrent write conflicts."""
        self.ensure_one()
        now = fields.Datetime.now()
        throttle = (
            HTTP_LISTENING_TOUCH_THROTTLE_SECONDS
            if throttle_seconds is None
            else throttle_seconds
        )
        if (
            not force
            and throttle
            and self.http_listening_last_at
            and (now - self.http_listening_last_at).total_seconds() < throttle
        ):
            return
        try:
            with self.env.cr.savepoint():
                self.sudo().with_context(
                    tracking_disable=True,
                    mail_notrack=True,
                ).write({'http_listening_last_at': now})
        except Exception as exc:
            if self._is_pg_concurrency_error(exc):
                _logger.debug(
                    'Concurrent update skipped for http_listening_last_at on %s',
                    self.name,
                )
                return
            raise

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

    @api.model
    def _find_zkteco_adms_device(self, serial):
        """Match an active ZKTeco device by ADMS serial number (SN)."""
        serial = (serial or '').strip()
        if not serial:
            return self.browse()
        Device = self.sudo()
        device = Device.search([
            ('api_type', '=', 'zkteco'),
            ('zkteco_adms_enabled', '=', True),
            ('active', '=', True),
            ('zkteco_serial_number', '=', serial),
        ], limit=1)
        if device:
            return device
        # Case-insensitive fallback (devices sometimes vary SN casing).
        candidates = Device.search([
            ('api_type', '=', 'zkteco'),
            ('zkteco_adms_enabled', '=', True),
            ('active', '=', True),
            ('zkteco_serial_number', '!=', False),
        ])
        serial_upper = serial.upper()
        return candidates.filtered(
            lambda d: (d.zkteco_serial_number or '').strip().upper() == serial_upper
        )[:1]

    def action_regenerate_http_listening_token(self):
        self.ensure_one()
        self.write({'http_listening_token': self._generate_http_listening_token()})
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('api_type') == 'zkteco':
                vals.setdefault('device_port', 4370)
                vals.setdefault('http_listening_enabled', False)
                vals.setdefault('auto_sync', False)
                vals.setdefault('zkteco_adms_enabled', True)
            if vals.get('http_listening_enabled'):
                if 'auto_sync' not in vals:
                    vals['auto_sync'] = False
                if not vals.get('http_listening_token'):
                    vals['http_listening_token'] = self._generate_http_listening_token()
                if not vals.get('http_listening_allowed_ips') and vals.get('device_ip'):
                    vals['http_listening_allowed_ips'] = vals['device_ip']
            if vals.get('zkteco_adms_enabled') and vals.get('api_type', 'zkteco') == 'zkteco':
                if 'auto_sync' not in vals:
                    vals['auto_sync'] = False
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('http_listening_enabled') and 'auto_sync' not in vals:
            vals = dict(vals, auto_sync=False)
        if vals.get('zkteco_adms_enabled') and 'auto_sync' not in vals:
            vals = dict(vals, auto_sync=False)
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
        """Return True when recent HTTP / ADMS pushes indicate live sync is healthy."""
        self.ensure_one()
        now = now or fields.Datetime.now()
        push_enabled = False
        if self.api_type == 'hikvision' and self.http_listening_enabled:
            push_enabled = True
        elif self.api_type == 'zkteco' and self.zkteco_adms_enabled:
            push_enabled = True
        if not push_enabled or not self.http_listening_last_at:
            return False
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

    @api.onchange('api_type')
    def _onchange_api_type_defaults(self):
        if self.api_type == 'zkteco':
            if not self.device_port or self.device_port in (80, 443):
                self.device_port = 4370
            self.http_listening_enabled = False
            self.auto_sync = False
            self.zkteco_adms_enabled = True
        elif self.api_type == 'hikvision':
            if not self.device_port or self.device_port == 4370:
                self.device_port = 80

    def _get_device_connector(self):
        self.ensure_one()
        return get_device_connector(self)

    def action_test_connection(self):
        self.ensure_one()
        if self.api_type == 'zkteco':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('ZKTeco uses ADMS push'),
                    'message': _(
                        'Do not use Test Connection / Sync on Odoo.sh (needs pyzk + LAN). '
                        'Set the device Cloud/ADMS URL to %(url)s and Serial Number %(sn)s, '
                        'or run the local ADMS bridge (scripts/zkteco_attendance_service).',
                        url=self.zkteco_adms_url or '/iclock/',
                        sn=self.zkteco_serial_number or _('(set SN on this device)'),
                    ),
                    'type': 'info',
                    'sticky': True,
                },
            }
        connector = self._get_device_connector()
        result = connector.test_connection()
        detail = ''
        if isinstance(result, dict) and result:
            detail = ' — ' + ', '.join(f'{key}={value}' for key, value in result.items())
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Connection OK'),
                'message': _('Connected to %(device)s%(detail)s', device=self.name, detail=detail),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_sync_now(self):
        self.ensure_one()
        if self.api_type == 'zkteco':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Use ADMS push (like Hikvision)'),
                    'message': _(
                        'ZKTeco attendance should arrive automatically when someone punches. '
                        'Configure the device ADMS URL (%(url)s) and Serial %(sn)s. '
                        'Sync Now is only for on-LAN pyzk pull, which Odoo.sh cannot do.',
                        url=self.zkteco_adms_url or '/iclock/',
                        sn=self.zkteco_serial_number or _('(missing)'),
                    ),
                    'type': 'warning',
                    'sticky': True,
                },
            }
        self._auto_sync_device()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sync finished'),
                'message': self.last_sync_message or _('Device sync completed.'),
                'type': 'success' if self.sync_status == 'success' else 'warning',
                'sticky': False,
            },
        }

    def ingest_external_attendance_events(self, events):
        """XML-RPC / bridge entry: ingest already-normalized ZK/Hikvision events.

        ``events`` is a list of dicts with keys compatible with
        ``HikvisionClient.normalize_access_event`` /
        ``ZktecoClient.normalize_attendance_row``.
        """
        self.ensure_one()
        connector = self._get_device_connector()
        created = self.env['fingerprint.device.log']
        stats = {
            'fetched': len(events or []),
            'stored': 0,
            'ignored': 0,
            'duplicates': 0,
            'unmapped': 0,
            'skipped': 0,
        }
        for raw_event in events or []:
            event = dict(raw_event or {})
            event_time = event.get('event_time')
            if isinstance(event_time, str) and event_time:
                event['event_time'] = fields.Datetime.to_datetime(event_time)
            log, action, _reason = connector._ingest_normalized_event(
                event, process_immediately=False,
            )
            if action == 'stored' and log:
                created |= log
                stats['stored'] += 1
                if not log.employee_id:
                    stats['unmapped'] += 1
            elif action == 'ignored':
                stats['ignored'] += 1
            elif action == 'duplicate':
                stats['duplicates'] += 1
            else:
                stats['skipped'] += 1
        if created:
            created._process_pending_logs()
        self.write({
            'last_sync_at': fields.Datetime.now(),
            'last_sync_message': _(
                'Bridge ingest: fetched %(fetched)s | stored %(stored)s | '
                'ignored %(ignored)s | duplicates %(duplicates)s | '
                'unmapped %(unmapped)s | skipped %(skipped)s',
                **stats,
            ),
            'sync_status': 'success',
        })
        return stats

    def _sync_device(self):
        self.ensure_one()
        self.sync_status = 'running'
        try:
            connector = self._get_device_connector()
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

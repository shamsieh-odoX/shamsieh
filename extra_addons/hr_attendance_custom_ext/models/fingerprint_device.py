# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

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
        string='Store Ignored Events',
        default=False,
        help='When enabled, door/system events are saved with state Ignored. '
             'When disabled, they are skipped entirely.',
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

    def action_sync_now(self):
        for device in self:
            device._sync_device()
        return True

    def action_process_logs(self):
        for device in self:
            device.log_ids.filtered(lambda log: log.state == 'draft')._process_pending_logs()
        return True

    def action_sync_and_process(self):
        for device in self:
            device._sync_device()
            device._refresh_log_employee_mappings()
            device.log_ids.filtered(lambda log: log.state == 'draft')._process_pending_logs()
        return True

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

    def action_reprocess_errors(self):
        for device in self:
            errors = device.log_ids.filtered(lambda log: log.state == 'error')
            errors.action_reset_to_draft()
            errors._process_pending_logs()
        return True

    def action_test_connection(self):
        self.ensure_one()
        connector = HikvisionConnector(self)
        connector.test_connection()
        if self.api_type == 'hikvision':
            caps = connector.get_capabilities()
            supported = sum(1 for meta in caps.values() if meta.get('supported'))
            message = _('Device connected. %s ISAPI endpoint(s) available.', supported)
        else:
            message = _('Device connection OK.')
        self.last_sync_message = message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Connection OK'),
                'message': message,
                'type': 'success',
                'sticky': False,
            },
        }

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
        }

    def action_view_logs(self):
        return self._action_view_logs_domain()

    def action_view_draft_logs(self):
        return self._action_view_logs_domain([('state', '=', 'draft')])

    def action_view_error_logs(self):
        return self._action_view_logs_domain([('state', '=', 'error')])

    def action_view_processed_logs(self):
        return self._action_view_logs_domain([('state', '=', 'processed')])

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
        devices = self.search([('active', '=', True), ('auto_sync', '=', True)])
        for device in devices:
            try:
                device._sync_device()
            except UserError:
                continue

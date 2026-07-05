# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services.hikvision_connector import HikvisionConnector


class FingerprintDevice(models.Model):
    _name = 'fingerprint.device'
    _description = 'Fingerprint Device'
    _order = 'name'

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
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
    log_count = fields.Integer(compute='_compute_log_count')

    @api.depends('log_ids')
    def _compute_log_count(self):
        for device in self:
            device.log_count = len(device.log_ids)

    def action_sync_now(self):
        for device in self:
            device._sync_device()
        return True

    def action_test_connection(self):
        self.ensure_one()
        connector = HikvisionConnector(self)
        connector.test_connection()
        caps = connector.get_capabilities()
        self.last_sync_message = str(caps)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Connection OK'),
                'message': _('Device responded. See last sync message for capabilities.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def _sync_device(self):
        self.ensure_one()
        self.sync_status = 'running'
        try:
            connector = HikvisionConnector(self)
            logs = connector.sync_device_logs()
            processed = logs._process_pending_logs()
            self.write({
                'sync_status': 'success',
                'last_sync_at': fields.Datetime.now(),
                'last_sync_message': _(
                    'Imported %(imported)s log(s), processed %(processed)s.',
                    imported=len(logs),
                    processed=len(processed),
                ),
            })
        except Exception as exc:
            self.write({
                'sync_status': 'error',
                'last_sync_at': fields.Datetime.now(),
                'last_sync_message': str(exc),
            })
            raise UserError(_('Sync failed: %s', exc)) from exc

    @api.model
    def _cron_sync_all(self):
        devices = self.search([('active', '=', True), ('auto_sync', '=', True)])
        for device in devices:
            try:
                device._sync_device()
            except UserError:
                continue

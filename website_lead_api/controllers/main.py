# -*- coding: utf-8 -*-

import json
import logging
import re
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)

RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_SECONDS = 3600
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

# Extra label aliases for older website payloads.
SERVICE_INTEREST_EXTRA_ALIASES = {
    'odoo implementation': 'implementation',
    'support & maintenance': 'support',
    'cloud hosting': 'other',
}


class WebsiteLeadController(http.Controller):

    def _json_response(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _client_ip(self):
        forwarded = request.httprequest.headers.get('X-Forwarded-For', '')
        if forwarded:
            return forwarded.split(',')[0].strip()
        return request.httprequest.remote_addr

    def _get_expected_api_key(self):
        return request.env['ir.config_parameter'].sudo().get_param('website.lead_api_key')

    def _validate_api_key(self):
        expected = self._get_expected_api_key()
        if not expected:
            return False, 'API key not configured'
        provided = request.httprequest.headers.get('X-API-Key', '')
        if not provided or provided != expected:
            return False, 'Unauthorized'
        return True, None

    def _is_rate_limited(self, ip_address):
        Log = request.env['website.lead.submission.log'].sudo()
        window_start = fields.Datetime.now() - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
        recent_count = Log.search_count([
            ('ip_address', '=', ip_address),
            ('create_date', '>=', window_start),
        ])
        return recent_count >= RATE_LIMIT_MAX

    def _parse_json_body(self):
        raw = request.httprequest.data
        if not raw:
            return None, 'Empty request body'
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None, 'Invalid JSON body'
        if not isinstance(data, dict):
            return None, 'JSON body must be an object'
        return data, None

    def _validate_fields(self, data):
        for field_name in ('name', 'email', 'message'):
            value = (data.get(field_name) or '').strip()
            if not value:
                return f'Missing required field: {field_name}'
        email = data.get('email', '').strip()
        if not EMAIL_RE.match(email):
            return 'Invalid email address'
        return None

    def _resolve_country_id(self, country_value):
        raw = (country_value or '').strip()
        if not raw or raw.lower() == 'other':
            return False
        Country = request.env['res.country'].sudo()
        country = Country.search([('code', '=ilike', raw)], limit=1)
        if country:
            return country.id
        country = Country.search([('name', '=ilike', raw)], limit=1)
        return country.id if country else False

    def _selection_aliases(self, field_name, extra=None):
        selection = request.env['crm.lead']._fields[field_name].selection
        if callable(selection):
            selection = selection(request.env['crm.lead'])
        aliases = {key.lower(): key for key, _label in selection}
        aliases.update({label.lower(): key for key, label in selection})
        if extra:
            aliases.update(extra)
        return aliases

    def _resolve_service_interest(self, service_value):
        raw = (service_value or '').strip()
        if not raw:
            return False
        aliases = self._selection_aliases('service_interest', SERVICE_INTEREST_EXTRA_ALIASES)
        return aliases.get(raw.lower(), False)

    def _resolve_preferred_contact_method(self, method_value):
        raw = (method_value or '').strip()
        if not raw:
            return False
        aliases = self._selection_aliases('preferred_contact_method')
        return aliases.get(raw.lower(), False)

    def _build_lead_vals(self, data):
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        company = (data.get('company') or '').strip()
        phone = (data.get('phone') or '').strip()
        service_interest = self._resolve_service_interest(data.get('service'))
        preferred_contact_method = self._resolve_preferred_contact_method(
            data.get('contact_method')
        )
        country_id = self._resolve_country_id(data.get('country'))

        channel = request.env.ref('crm_custom_ext.channel_website', raise_if_not_found=False)
        utm_source = request.env.ref('crm_custom_ext.utm_source_website_shamsieh', raise_if_not_found=False)

        vals = {
            'name': f"Website Inquiry — {company or name}",
            'contact_name': name,
            'email_from': email,
            'phone': phone,
            'partner_name': company,
            'type': 'lead',
        }
        if country_id:
            vals['country_id'] = country_id
        if service_interest:
            vals['service_interest'] = service_interest
        if preferred_contact_method:
            vals['preferred_contact_method'] = preferred_contact_method
        if channel:
            vals['channel_id'] = channel.id
        if utm_source:
            vals['source_id'] = utm_source.id
        return vals

    def _post_inquiry_message(self, lead, message):
        body = Markup('<p>%s</p>') % escape(message).replace('\n', Markup('<br/>'))
        lead.message_post(
            body=body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

    @http.route(
        '/api/website/lead',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        cors='*',
    )
    def create_website_lead(self, **kwargs):
        try:
            data, parse_error = self._parse_json_body()
            if parse_error:
                return self._json_response({'success': False, 'error': parse_error}, status=400)

            honeypot = (data.get('website') or '').strip()
            if honeypot:
                return self._json_response({'success': True})

            ok, auth_error = self._validate_api_key()
            if not ok:
                status = 401 if auth_error == 'Unauthorized' else 500
                return self._json_response({'success': False, 'error': auth_error}, status=status)

            ip_address = self._client_ip()
            if self._is_rate_limited(ip_address):
                return self._json_response(
                    {'success': False, 'error': 'Rate limit exceeded'},
                    status=429,
                )

            field_error = self._validate_fields(data)
            if field_error:
                return self._json_response({'success': False, 'error': field_error}, status=400)

            lead_vals = self._build_lead_vals(data)
            lead = request.env['crm.lead'].sudo().create(lead_vals)

            message = data.get('message', '').strip()
            if message:
                self._post_inquiry_message(lead, message)

            request.env['website.lead.submission.log'].sudo().create({
                'ip_address': ip_address,
                'email': data.get('email', '').strip(),
                'lead_id': lead.id,
            })

            return self._json_response({
                'success': True,
                'lead_id': lead.id,
                'lead_ref': lead.lead_ref or lead.name,
            })
        except Exception as exc:
            _logger.exception('Website lead API error')
            return self._json_response({'success': False, 'error': str(exc)}, status=500)

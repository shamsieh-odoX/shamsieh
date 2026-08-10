# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    departure_type = env.ref(
        'hr_holidays_custom_ext.leave_type_hourly_departure',
        raise_if_not_found=False,
    )
    if not departure_type:
        return
    companies = env['res.company'].sudo().search([
        ('hourly_departure_type_id', '=', False),
    ])
    if companies:
        companies.write({'hourly_departure_type_id': departure_type.id})

import odoo
from odoo.tools import config
config.parse_config(['-c', 'debian/odoo.conf', '-d', 'odoo19'])
registry = odoo.registry('odoo19')
with registry.cursor() as cr:
    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
    env['res.company'].search([])._ensure_overtime_types()
    cr.commit()
    for t in env['hr.overtime.type'].sudo().search([]):
        print(t.id, t.name, t.category, t.rate_multiplier, t.company_id.id, t.active)
    for c in env['res.company'].search([]):
        print('Company', c.id, c.name,
              'reg', c.overtime_default_type_id.id,
              'we', c.overtime_weekend_type_id.id,
              'off', c.overtime_holiday_type_id.id)
    req = env['hr.overtime.request'].browse(23)
    if req.exists():
        ot = req._resolve_overtime_type_for_period()
        print('Request 23', req.start_datetime, 'weekday', req.start_datetime.weekday(),
              '->', ot.name, ot.rate_multiplier, ot.category)

# -*- coding: utf-8 -*-


def _reload_ar_translations(env, module_name):
    lang = env['res.lang'].with_context(active_test=False).search(
        [('code', 'in', ['ar_001', 'ar'])], limit=1,
    )
    if not lang:
        return
    mod = env['ir.module.module'].search([('name', '=', module_name)], limit=1)
    if mod:
        mod._update_translations(filter_lang=[lang.code], overwrite=True)


def _configure_two_step_leave_types(env):
    """Paid / annual leave: manager then officer/GM. Employees only apply."""
    LeaveType = env['hr.leave.type'].sudo()
    leave_types = LeaveType.search([
        ('requires_allocation', '=', True),
        '|', '|', '|',
        ('name', 'ilike', 'paid time off'),
        ('name', 'ilike', 'legal leave'),
        ('name', 'ilike', 'annual'),
        ('name', 'ilike', 'pto'),
    ])
    if leave_types:
        leave_types.write({'leave_validation_type': 'both'})


def post_init_hook(env):
    _configure_two_step_leave_types(env)
    _reload_ar_translations(env, 'hr_holidays_custom_ext')

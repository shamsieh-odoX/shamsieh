# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """noupdate rules from the first install must be corrected on upgrade."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Rule = env['ir.rule'].sudo()

    def set_rule(xmlid, values):
        rule = env.ref(xmlid, raise_if_not_found=False)
        if rule:
            rule.write(values)

    group = env.ref('hr_employee_own_data.group_hr_own_data', raise_if_not_found=False)
    if not group:
        return

    set_rule('hr_employee_own_data.hr_employee_own_data_rule', {
        'name': 'Employee: manage own data write',
        'domain_force': "[('user_id', '=', user.id)]",
        'perm_read': False,
        'perm_write': True,
        'perm_create': False,
        'perm_unlink': False,
    })
    set_rule('hr_employee_own_data.hr_version_own_data_rule', {
        'name': 'Employee version: manage own data write',
        'domain_force': "[('employee_id.user_id', '=', user.id)]",
        'perm_read': False,
        'perm_write': True,
        'perm_create': False,
        'perm_unlink': False,
    })
    set_rule('hr_employee_own_data.resource_resource_own_data_rule', {
        'name': 'Resource: manage own employee resource write',
        'domain_force': "[('user_id', '=', user.id)]",
        'perm_read': False,
        'perm_write': True,
        'perm_create': False,
        'perm_unlink': False,
    })

# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import SUPERUSER_ID, api

_OWN_OR_COMPANY_DOMAIN = (
    "['|', ('company_id', 'in', company_ids), ('employee_id.user_id', '=', user.id)]"
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in (
        'hr_loans_advances.hr_employee_loan_comp_rule',
        'hr_loans_advances.hr_employee_advance_comp_rule',
    ):
        rule = env.ref(xmlid, raise_if_not_found=False)
        if rule:
            rule.domain_force = _OWN_OR_COMPANY_DOMAIN

# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

_logger = logging.getLogger(__name__)

STRUCTURE_XMLIDS = (
    'hr_payroll.structure_base',
    'l10n_jo_hr_payroll.l10n_jo_hr_payroll_structure_jo_employee_salary',
    'l10n_jo_hr_payroll.hr_payroll_structure_jordan_monthly',
    'l10n_jo_hr_payroll.l10n_jo_hr_payroll_structure_jordan_employee_monthly_pay',
)

RULE_XMLIDS = (
    'hr_payroll_custom_ext.salary_rule_unworked_deduction',
    'hr_payroll_custom_ext.salary_rule_loan_deduction',
    'hr_payroll_custom_ext.salary_rule_advance_deduction',
)


def _get_target_structures(env):
    """Resolve structures that should receive custom deduction rules."""
    structures = env['hr.payroll.structure']
    for xmlid in STRUCTURE_XMLIDS:
        structure = env.ref(xmlid, raise_if_not_found=False)
        if structure:
            structures |= structure
    jordan = env['hr.payroll.structure'].search([
        '|',
        ('name', 'ilike', 'Jordan: Monthly Pay'),
        ('code', 'ilike', 'JO'),
    ])
    return structures | jordan


def _link_rules_to_structures(env):
    rules = env['hr.salary.rule']
    for xmlid in RULE_XMLIDS:
        rule = env.ref(xmlid, raise_if_not_found=False)
        if rule:
            rules |= rule
    if not rules:
        return

    structures = _get_target_structures(env)
    if not structures:
        _logger.warning(
            'hr_payroll_custom_ext: no payroll structure found to attach salary rules.'
        )
        return

    # Keep the XML-created rules on the first structure, then clone for others.
    primary = structures[0]
    for rule in rules:
        if rule.struct_id != primary:
            rule.struct_id = primary.id

    for structure in structures[1:]:
        for rule in rules:
            existing = env['hr.salary.rule'].search([
                ('struct_id', '=', structure.id),
                ('code', '=', rule.code),
            ], limit=1)
            if existing:
                existing.write({
                    'condition_select': rule.condition_select,
                    'condition_python': rule.condition_python,
                    'amount_select': rule.amount_select,
                    'amount_python_compute': rule.amount_python_compute,
                    'sequence': rule.sequence,
                    'category_id': rule.category_id.id,
                    'active': True,
                })
                continue
            rule.copy({
                'struct_id': structure.id,
                'name': rule.name,
                'code': rule.code,
            })


def post_init_hook(env):
    _link_rules_to_structures(env)

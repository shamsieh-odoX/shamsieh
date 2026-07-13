# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from datetime import date

_logger = logging.getLogger(__name__)

JORDAN_STRUCTURE_XMLIDS = (
    'l10n_jo_hr_payroll.l10n_jo_hr_payroll_structure_jo_employee_salary',
    'l10n_jo_hr_payroll.hr_payroll_structure_jordan_monthly',
    'l10n_jo_hr_payroll.l10n_jo_hr_payroll_structure_jordan_employee_monthly_pay',
)

OVERTIME_RULE_CODES = ('OVERTIME', 'OT')


def get_jordan_payroll_structure(env):
    """Resolve Jordan: Monthly Pay structure from localization or by name."""
    for xmlid in JORDAN_STRUCTURE_XMLIDS:
        structure = env.ref(xmlid, raise_if_not_found=False)
        if structure:
            return structure
    return env['hr.payroll.structure'].search([
        '|',
        ('name', 'ilike', 'Jordan: Monthly Pay'),
        ('code', 'ilike', 'JOMONTHLY'),
    ], limit=1)


def post_init_hook(env):
    _ensure_jordan_rule_parameter_defaults(env)
    structure = get_jordan_payroll_structure(env)
    if not structure:
        _logger.warning(
            'hr_payroll_jo_custom_ext: Jordan payroll structure not found. '
            'Install l10n_jo_hr_payroll and upgrade this module to attach salary rules.'
        )
        return
    _link_custom_rules_to_structure(env, structure)
    _ensure_overtime_rule(env, structure)


def _ensure_jordan_rule_parameter_defaults(env):
    """Set Jordan rule parameter values for the current year when missing."""
    if 'hr.rule.parameter' not in env:
        return
    jo_country = env.ref('base.jo', raise_if_not_found=False)
    if not jo_country:
        return
    current_year = date.today().year
    defaults = [
        ('Jordan Social Security Employee Deduction Rate %', 7.5),
        ('Jordan Social Security Employer Contribution Rate %', 14.25),
    ]
    RuleParameter = env['hr.rule.parameter']
    RuleParameterValue = env['hr.rule.parameter.value']
    for name, value in defaults:
        parameter = RuleParameter.search([
            ('name', '=', name),
            ('country_id', '=', jo_country.id),
        ], limit=1)
        if not parameter:
            continue
        existing = RuleParameterValue.search([
            ('rule_parameter_id', '=', parameter.id),
            ('date_from', '<=', date(current_year, 12, 31)),
            '|',
            ('date_to', '=', False),
            ('date_to', '>=', date(current_year, 1, 1)),
        ], limit=1)
        if existing:
            continue
        RuleParameterValue.create({
            'rule_parameter_id': parameter.id,
            'date_from': date(current_year, 1, 1),
            'parameter_value': str(value),
        })


def _link_custom_rules_to_structure(env, structure):
    rule_xmlids = (
        'hr_payroll_jo_custom_ext.hr_salary_rule_jo_absence',
        'hr_payroll_jo_custom_ext.hr_salary_rule_jo_unpaid',
        'hr_payroll_jo_custom_ext.hr_salary_rule_jo_loan',
        'hr_payroll_jo_custom_ext.hr_salary_rule_jo_advance',
        'hr_payroll_jo_custom_ext.hr_salary_rule_jo_overtime',
    )
    for xmlid in rule_xmlids:
        rule = env.ref(xmlid, raise_if_not_found=False)
        if rule and rule.struct_id != structure:
            rule.struct_id = structure.id


def _ensure_overtime_rule(env, structure):
    existing = env['hr.salary.rule'].search([
        ('struct_id', '=', structure.id),
        ('code', 'in', list(OVERTIME_RULE_CODES)),
    ], limit=1)
    if existing:
        overtime_rule = env.ref(
            'hr_payroll_jo_custom_ext.hr_salary_rule_jo_overtime',
            raise_if_not_found=False,
        )
        if overtime_rule and overtime_rule.active:
            overtime_rule.active = False
        return
    overtime_rule = env.ref(
        'hr_payroll_jo_custom_ext.hr_salary_rule_jo_overtime',
        raise_if_not_found=False,
    )
    if overtime_rule:
        overtime_rule.write({'struct_id': structure.id, 'active': True})

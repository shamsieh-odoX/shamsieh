# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

_logger = logging.getLogger(__name__)

RULE_DEFINITIONS = (
    {
        'code': 'UNWORKED_DED',
        'name': 'Unworked Time Deduction',
        'sequence': 150,
        'input_code': 'UNWORKED_DEDUCTION',
    },
    {
        'code': 'LOAN_DED',
        'name': 'Loan Installment',
        'sequence': 160,
        'input_code': 'LOAN_DEDUCTION',
    },
    {
        'code': 'ADV_DED',
        'name': 'Salary Advance Recovery',
        'sequence': 170,
        'input_code': 'ADVANCE_DEDUCTION',
    },
)

STRUCTURE_XMLIDS = (
    'hr_payroll.structure_base',
    'l10n_jo_hr_payroll.l10n_jo_hr_payroll_structure_jo_employee_salary',
    'l10n_jo_hr_payroll.hr_payroll_structure_jordan_monthly',
    'l10n_jo_hr_payroll.l10n_jo_hr_payroll_structure_jordan_employee_monthly_pay',
)


def _get_or_create_category(env):
    Category = env['hr.salary.rule.category'].sudo()
    category = Category.search([('code', '=', 'CUSTOM_DED')], limit=1)
    if category:
        return category
    # Prefer nesting under standard DED when available.
    parent = env.ref('hr_payroll.DED', raise_if_not_found=False)
    vals = {
        'name': 'Custom Deductions',
        'code': 'CUSTOM_DED',
    }
    if parent:
        vals['parent_id'] = parent.id
    return Category.create(vals)


def _get_target_structures(env):
    Structure = env['hr.payroll.structure'].sudo()
    structures = Structure.browse()
    for xmlid in STRUCTURE_XMLIDS:
        structure = env.ref(xmlid, raise_if_not_found=False)
        if structure:
            structures |= structure
    structures |= Structure.search([
        '|',
        ('name', 'ilike', 'Jordan'),
        ('name', 'ilike', 'Monthly Pay'),
    ])
    if not structures:
        # Fallback: every structure in the DB (company may use a custom name).
        structures = Structure.search([])
    return structures


def _rule_vals(category, structure, definition):
    input_code = definition['input_code']
    return {
        'name': definition['name'],
        'code': definition['code'],
        'sequence': definition['sequence'],
        'category_id': category.id,
        'struct_id': structure.id,
        'condition_select': 'python',
        'condition_python': "result = inputs.get('%s', 0)" % input_code,
        'amount_select': 'code',
        'amount_python_compute': "result = -(inputs.get('%s') or 0)" % input_code,
        'active': True,
    }


def _ensure_custom_deduction_rules(env):
    """Create/update deduction rules on all available payroll structures.

    Best-effort: never raise — module install must not fail because of this.
    """
    try:
        category = _get_or_create_category(env)
        structures = _get_target_structures(env)
        if not structures:
            _logger.warning(
                'hr_payroll_custom_ext: no hr.payroll.structure found; '
                'salary rules will be created after a structure exists.'
            )
            return

        Rule = env['hr.salary.rule'].sudo()
        for structure in structures:
            for definition in RULE_DEFINITIONS:
                existing = Rule.search([
                    ('struct_id', '=', structure.id),
                    ('code', '=', definition['code']),
                ], limit=1)
                vals = _rule_vals(category, structure, definition)
                if existing:
                    existing.write(vals)
                else:
                    Rule.create(vals)
        _logger.info(
            'hr_payroll_custom_ext: ensured deduction rules on %s structure(s).',
            len(structures),
        )
    except Exception:
        _logger.exception(
            'hr_payroll_custom_ext: failed to ensure custom deduction rules'
        )


def post_init_hook(env):
    _ensure_custom_deduction_rules(env)

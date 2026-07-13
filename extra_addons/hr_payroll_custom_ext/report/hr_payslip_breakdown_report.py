# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date


PAYSLIP_BUCKETS = {
    'basic': {
        'label': 'Basic Salary',
        'codes': ['BASIC', 'BASE', 'BASICWAGE'],
        'categories': ['BASIC'],
        'kinds': ['earning'],
    },
    'allowances': {
        'label': 'Allowances',
        'codes': ['ALW', 'ALLOWANCE'],
        'categories': ['ALW'],
        'kinds': ['earning'],
    },
    'bonuses': {
        'label': 'Bonuses',
        'codes': ['BONUS'],
        'categories': ['ALW', 'BASIC'],
        'kinds': ['earning'],
    },
    'overtime': {
        'label': 'Overtime Pay',
        'codes': ['OVERTIME', 'OT'],
        'input_codes': ['OVERTIME'],
        'kinds': ['earning'],
    },
    'loans': {
        'label': 'Loans',
        'codes': ['LOAN'],
        'categories': ['DED'],
        'kinds': ['deduction'],
    },
    'advances': {
        'label': 'Advances',
        'codes': ['ADV', 'ADVANCE'],
        'categories': ['DED'],
        'kinds': ['deduction'],
    },
    'social_security': {
        'label': 'Social Security',
        'codes': ['SS', 'SSC', 'SOCIAL'],
        'categories': ['DED'],
        'kinds': ['deduction'],
    },
    'income_tax': {
        'label': 'Income Tax',
        'codes': ['TAX', 'IT', 'PIT'],
        'categories': ['DED'],
        'kinds': ['deduction'],
    },
    'net': {
        'label': 'Net Pay',
        'codes': ['NET'],
        'categories': ['NET'],
        'kinds': ['net'],
    },
}


class ReportHrPayrollCustomExtReportPayslipBreakdown(models.AbstractModel):
    _name = 'report.hr_payroll_custom_ext.report_payslip_breakdown'
    _description = 'Payslip Breakdown Report'

    def _bucket_line_amount(self, line, bucket_key):
        bucket = PAYSLIP_BUCKETS[bucket_key]
        code = (line.code or '').upper()
        category_code = (line.category_id.code or '').upper() if line.category_id else ''
        if code in bucket.get('codes', []):
            return abs(line.total)
        if category_code in bucket.get('categories', []) and bucket_key in ('allowances', 'bonuses'):
            if bucket_key == 'bonuses' and code in PAYSLIP_BUCKETS['allowances']['codes']:
                return 0.0
            if bucket_key == 'allowances' and code in PAYSLIP_BUCKETS['bonuses']['codes']:
                return 0.0
        if category_code in bucket.get('categories', []) and bucket_key not in ('allowances', 'bonuses'):
            if code in PAYSLIP_BUCKETS['basic']['codes'] and bucket_key != 'basic':
                return 0.0
            return abs(line.total)
        for prefix in bucket.get('codes', []):
            if code.startswith(prefix):
                return abs(line.total)
        return 0.0

    def _bucket_input_amount(self, input_line, bucket_key):
        bucket = PAYSLIP_BUCKETS[bucket_key]
        input_code = (input_line.input_type_id.code or '').upper() if input_line.input_type_id else ''
        name = (input_line.name or '').upper()
        if input_code in bucket.get('input_codes', []) or input_code in bucket.get('codes', []):
            return abs(input_line.amount)
        for code in bucket.get('codes', []):
            if code in name:
                return abs(input_line.amount)
        return 0.0

    def _empty_buckets(self):
        return {key: 0.0 for key in PAYSLIP_BUCKETS}

    def _summarize_payslip(self, payslip):
        buckets = self._empty_buckets()
        other_earnings = 0.0
        other_deductions = 0.0
        matched_line_ids = set()

        for line in payslip.line_ids:
            matched = False
            for bucket_key in PAYSLIP_BUCKETS:
                amount = self._bucket_line_amount(line, bucket_key)
                if amount:
                    buckets[bucket_key] += amount
                    matched_line_ids.add(line.id)
                    matched = True
                    break
            if matched:
                continue
            amount = abs(line.total)
            if not amount:
                continue
            category_code = (line.category_id.code or '').upper() if line.category_id else ''
            if category_code in ('DED',) or line.total < 0:
                other_deductions += amount
            elif category_code in ('BASIC', 'ALW', 'GROSS') or line.total > 0:
                other_earnings += amount

        for input_line in payslip.input_line_ids:
            amount = self._bucket_input_amount(input_line, 'overtime')
            if amount:
                buckets['overtime'] += amount

        if not buckets['net']:
            net_line = payslip.line_ids.filtered(lambda l: (l.code or '').upper() == 'NET')[:1]
            if net_line:
                buckets['net'] = abs(net_line.total)
            elif payslip.net_wage:
                buckets['net'] = abs(payslip.net_wage)

        gross = sum(
            buckets[key] for key in ('basic', 'allowances', 'bonuses', 'overtime')
        ) + other_earnings
        total_deductions = sum(
            buckets[key] for key in ('loans', 'advances', 'social_security', 'income_tax')
        ) + other_deductions
        if not buckets['net'] and gross:
            buckets['net'] = max(gross - total_deductions, 0.0)

        return {
            'employee': payslip.employee_id,
            'department': payslip.employee_id.department_id,
            'payslip': payslip,
            'period_from': payslip.date_from,
            'period_to': payslip.date_to,
            'buckets': buckets,
            'bucket_labels': {key: cfg['label'] for key, cfg in PAYSLIP_BUCKETS.items()},
            'other_earnings': other_earnings,
            'other_deductions': other_deductions,
            'gross': gross,
            'total_deductions': total_deductions,
        }

    def _get_payslips(self, wizard_data):
        domain = [
            ('company_id', '=', wizard_data['company_id']),
            ('date_from', '>=', wizard_data['date_from']),
            ('date_to', '<=', wizard_data['date_to']),
            ('state', '=', wizard_data.get('payslip_state', 'done')),
        ]
        if wizard_data.get('department_id'):
            domain.append(('employee_id.department_id', '=', wizard_data['department_id']))
        if wizard_data.get('employee_ids'):
            domain.append(('employee_id', 'in', wizard_data['employee_ids']))
        return self.env['hr.payslip'].search(domain, order='employee_id, date_from')

    def _get_header_info(self, wizard_data):
        company = self.env['res.company'].browse(wizard_data['company_id'])
        department = self.env['hr.department'].browse(wizard_data['department_id']) if wizard_data.get('department_id') else False
        return {
            'company': company,
            'date_from': format_date(self.env, wizard_data['date_from']),
            'date_to': format_date(self.env, wizard_data['date_to']),
            'department': department.display_name if department else _('All Departments'),
            'payslip_state': wizard_data.get('payslip_state', 'done'),
        }

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data or not data.get('form'):
            raise UserError(_('Missing report parameters.'))
        wizard_data = data['form']
        payslips = self._get_payslips(wizard_data)
        employees_data = [self._summarize_payslip(payslip) for payslip in payslips]
        return {
            'doc_ids': docids,
            'doc_model': 'hr.payslip.breakdown.report.wizard',
            'docs': self.env['hr.payslip.breakdown.report.wizard'].browse(docids),
            'header': self._get_header_info(wizard_data),
            'employees_data': employees_data,
            'bucket_order': list(PAYSLIP_BUCKETS.keys()),
            'earning_keys': ['basic', 'allowances', 'bonuses', 'overtime'],
            'deduction_keys': ['loans', 'advances', 'social_security', 'income_tax'],
        }

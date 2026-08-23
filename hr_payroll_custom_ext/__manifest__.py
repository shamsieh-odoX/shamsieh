{
    'name': 'HR Payroll Custom Extensions',
    'version': '19.0.2.0.2',
    'category': 'Human Resources/Payroll',
    'summary': 'Auto-populate payslip deductions from attendance, loans, and salary advances',
    'author': 'Custom',
    'depends': [
        'hr_payroll',
        'hr_attendance_custom_ext',
        'hr_loans_advances',
    ],
    'data': [
        'data/hr_payroll_input_type_data.xml',
        'data/hr_salary_rule_link.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

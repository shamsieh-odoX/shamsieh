{
    'name': 'HR Payroll Custom Extensions',
    'version': '19.0.1.0.1',
    'category': 'Human Resources/Payroll',
    'summary': 'Payslip breakdown PDF report',
    'author': 'Custom',
    'depends': [
        'hr_payroll',
        'hr_overtime_payroll',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/hr_payslip_breakdown_report_wizard_views.xml',
        'report/hr_payslip_breakdown_report.xml',
        'views/hr_payroll_custom_menus.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

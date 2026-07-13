{
    'name': 'HR Overtime Payroll Integration',
    'version': '19.0.1.0.2',
    'category': 'Human Resources/Payroll',
    'summary': 'Push approved overtime costs to payslip inputs',
    'author': 'Custom',
    'depends': [
        'hr_overtime_management',
        'hr_payroll',
    ],
    'data': [
        'data/hr_payslip_input_type_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}

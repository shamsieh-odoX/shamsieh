{
    'name': 'HR Holidays Custom Approval',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Time Off',
    'summary': 'Org-chart based two-step Time Off approval (Manager→HR or HR→GM)',
    'author': 'Shamsieh',
    'license': 'LGPL-3',
    'depends': ['hr_holidays'],
    'data': [
        'security/hr_holidays_custom_approval_security.xml',
        'views/res_config_settings_views.xml',
        'views/hr_leave_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}

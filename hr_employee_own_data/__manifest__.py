{
    'name': 'HR Employee Own Data',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Employees',
    'summary': 'Access right so employees can edit their own Work, Resume, Personal, and Badges data',
    'author': 'Custom',
    'depends': [
        'hr',
        'hr_skills',
        'hr_gamification',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/hr_employee_views.xml',
        'views/hr_menus.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

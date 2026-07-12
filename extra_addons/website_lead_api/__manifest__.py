{
    'name': 'Website Lead API',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Public API endpoint for external website contact form submissions',
    'author': 'Custom',
    'depends': ['crm', 'crm_custom_ext', 'utm'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter_data.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

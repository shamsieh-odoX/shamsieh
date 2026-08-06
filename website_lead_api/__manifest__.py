{
    'name': 'Website Lead API',
    'version': '19.0.1.3.0',
    'category': 'Sales/CRM',
    'summary': 'Public API endpoint for external website contact form submissions',
    'author': 'Custom',
    'depends': ['crm', 'crm_custom_ext', 'utm', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/utm_source_data.xml',
        'views/crm_lead_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

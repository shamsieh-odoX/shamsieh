{
    'name': 'Documents Office Preview',
    'version': '19.0.1.0.0',
    'category': 'Productivity/Documents',
    'summary': 'Open Word/Excel/PowerPoint files on click in Documents',
    'author': 'Shamsieh',
    'license': 'LGPL-3',
    'depends': ['documents', 'web'],
    'installable': True,
    'application': False,
    'assets': {
        'web.assets_backend': [
            'documents_office_preview/static/src/**/*',
        ],
    },
}

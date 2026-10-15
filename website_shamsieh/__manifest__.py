{
    'name': 'Shamsieh Website',
    'version': '19.0.1.1.7',
    'category': 'Website',
    'summary': 'Shamsieh Solar/dusk brand website — products, platforms, talent',
    'author': 'Custom',
    'depends': ['website', 'website_crm'],
    'data': [
        'views/homepage.xml',
        'views/website_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'website_shamsieh/static/src/scss/shamsieh.scss',
            'website_shamsieh/static/src/js/shamsieh_home.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

{
    'name': 'Shamsieh Website',
    'version': '19.0.1.0.3',
    'category': 'Website',
    'summary': 'Company website homepage matching shamsieh.com brand and content',
    'author': 'Custom',
    'depends': ['website'],
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

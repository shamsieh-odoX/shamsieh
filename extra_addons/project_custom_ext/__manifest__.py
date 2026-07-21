{

    'name': 'Project Custom Extensions',

    'version': '19.0.2.1.10',

    'category': 'Services/Project',

    'summary': 'Security groups, progress, templates, and project fields per customization scope',

    'author': 'Custom',

    'depends': ['project', 'crm', 'hr_timesheet', 'sale', 'spreadsheet_dashboard_hr_timesheet'],

    'data': [

        'security/project_custom_security.xml',

        'security/ir.model.access.csv',

        'views/project_task_template_views.xml',

        'views/project_project_stage_views.xml',

        'views/project_task_type_views.xml',

        'views/project_project_views.xml',

        'views/project_task_views.xml',

        'views/project_task_search_views.xml',

        'views/project_dashboard_views.xml',

        'views/project_menus.xml',

        'data/project_task_template_data.xml',

    ],

    'post_init_hook': 'post_init_hook',

    'assets': {

        # Plain CSS so these never go through the Sass compiler.

        'web.assets_backend': [

            'project_custom_ext/static/src/css/project_custom.css',

            'project_custom_ext/static/src/compact_hours_field.xml',

            'project_custom_ext/static/src/compact_hours_field.js',

            'project_custom_ext/static/src/action_restore_form.js',

            'project_custom_ext/static/src/project_notifications.js',

        ],

        'web.assets_web_dark': [

            'project_custom_ext/static/src/css/project_custom.dark.css',

        ],

    },

    'installable': True,

    'application': False,

    'license': 'LGPL-3',

}



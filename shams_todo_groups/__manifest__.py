{
    'name': 'Shams To-Do Groups',
    'version': '19.0.1.0.23',
    'category': 'Productivity/To-Do',
    'summary': 'Shared To-Do groups with member-based task visibility',
    'author': 'Custom',
    'depends': [
        'base',
        'mail',
        'project_todo',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'views/todo_task_views.xml',
        'views/todo_group_views.xml',
        'views/todo_dashboard_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    # No web.assets_web_dark entry: production DB still had ir.asset rows pointing
    # at deleted scss that contained invalid "#" comments and broke the dark bundle.
    'assets': {
        'web.assets_backend': [
            'shams_todo_groups/static/src/css/shams_todo.css',
            'shams_todo_groups/static/src/css/shams_todo.dark.css',
        ],
    },
    'pre_init_hook': 'pre_init_hook',
}

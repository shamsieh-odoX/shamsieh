{
    'name': 'Shams To-Do Groups',
    'version': '19.0.1.0.16',
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
    'assets': {
        'web.assets_backend': [
            'shams_todo_groups/static/src/scss/shams_todo.scss',
            'shams_todo_groups/static/src/components/shams_todo_done_checkmark/shams_todo_done_checkmark.scss',
            'shams_todo_groups/static/src/components/shams_todo_done_checkmark/shams_todo_done_checkmark.xml',
            'shams_todo_groups/static/src/components/shams_todo_done_checkmark/shams_todo_done_checkmark.js',
        ],
        'web.assets_web_dark': [
            'shams_todo_groups/static/src/scss/shams_todo.dark.scss',
        ],
    },
}

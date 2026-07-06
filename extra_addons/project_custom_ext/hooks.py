# -*- coding: utf-8 -*-

import base64
from pathlib import Path


def _mark_closing_stages(env):
    """Mark Done/Cancelled (folded) stages as closing without hard-coded XML IDs."""
    env['project.task.type'].search([
        ('fold', '=', True),
        ('is_closing_stage', '=', False),
    ]).write({'is_closing_stage': True})
    ProjectStage = env['project.project.stage'].sudo()
    ProjectStage.search([
        ('fold', '=', True),
        ('is_closing_stage', '=', False),
    ]).write({'is_closing_stage': True})
    ProjectStage.search([
        ('name', 'in', ['Done', 'Cancelled']),
        ('is_closing_stage', '=', False),
    ]).write({'is_closing_stage': True})


def _override_spreadsheet_dashboard(env):
    """Apply custom dashboard JSON when the standard dashboard record exists."""
    dashboard = env.ref(
        'spreadsheet_dashboard_hr_timesheet.spreadsheet_dashboard_tasks',
        raise_if_not_found=False,
    )
    if not dashboard:
        return
    json_path = Path(__file__).resolve().parent / 'data/files/project_tasks_dashboard.json'
    if not json_path.is_file():
        return
    dashboard.sudo().write({
        'spreadsheet_binary_data': base64.b64encode(json_path.read_bytes()),
    })


def post_init_hook(env):
    """Mark folded stages as closing and recompute project progress for existing data."""
    _mark_closing_stages(env)
    for xmlid in ('task_template_impl_stage_done', 'task_template_crm_stage_done'):
        line = env.ref(f'project_custom_ext.{xmlid}', raise_if_not_found=False)
        if line:
            line.sudo().write({'name': 'Done', 'is_closing_stage': True, 'sequence': 50})
    projects = env['project.project'].search([])
    if projects:
        projects._compute_progress_and_hours()
        projects._compute_progress_range()
    _ensure_project_users_have_timesheet_access(env)
    _override_spreadsheet_dashboard(env)


def _ensure_project_users_have_timesheet_access(env):
    """Users with custom project roles need Timesheet User to see the task Timesheets tab."""
    timesheet_group = env.ref('hr_timesheet.group_hr_timesheet_user', raise_if_not_found=False)
    if not timesheet_group:
        return
    project_groups = env['res.groups'].browse([
        env.ref('project_custom_ext.group_project_edit_only').id,
        env.ref('project_custom_ext.group_project_create_move').id,
        env.ref('project_custom_ext.group_project_custom_manager').id,
    ])
    users = env['res.users'].search([
        ('share', '=', False),
        ('group_ids', 'in', project_groups.ids),
        ('group_ids', 'not in', timesheet_group.ids),
    ])
    if users:
        users.write({'group_ids': [(4, timesheet_group.id)]})

# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class ProjectTask(models.Model):
    _inherit = 'project.task'

    REVIEW_STATES = [
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('waiting_review', 'Waiting Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]

    owner_employee_id = fields.Many2one(
        'hr.employee',
        string='Owner Employee',
        index=True,
        tracking=True,
    )
    manager_id = fields.Many2one(
        'hr.employee',
        string='Manager',
        compute='_compute_manager_id',
        store=True,
        readonly=True,
    )
    is_shams_todo = fields.Boolean(
        string='Is To-Do',
        compute='_compute_is_shams_todo',
        store=True,
        index=True,
    )
    review_state = fields.Selection(
        selection=REVIEW_STATES,
        string='Review Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    actual_hours = fields.Float(string='Actual Hours', tracking=True)
    progress = fields.Integer(string='Progress (%)', tracking=True, default=0)
    work_done = fields.Html(string='Work Done')
    what_learned = fields.Html(string='What Learned')
    blockers = fields.Html(string='Blockers')
    tomorrow_plan = fields.Html(string='Tomorrow Plan')
    reviewed_by = fields.Many2one('res.users', string='Reviewed By', readonly=True, copy=False)
    reviewed_on = fields.Datetime(string='Reviewed On', readonly=True, copy=False)
    review_note = fields.Html(string='Review Note')
    visibility_user_ids = fields.Many2many(
        'res.users',
        'project_task_shams_visibility_user_rel',
        'task_id',
        'user_id',
        string='Visibility Users',
        compute='_compute_visibility_user_ids',
        store=True,
        index=True,
    )

    @api.depends(
        'owner_employee_id',
        'owner_employee_id.parent_id',
        'owner_employee_id.user_id',
        'is_shams_todo',
    )
    def _compute_visibility_user_ids(self):
        admin_group = self.env.ref(
            'shams_todo_management.group_shams_todo_admin',
            raise_if_not_found=False,
        )
        admin_users = admin_group.user_ids if admin_group else self.env['res.users']
        for task in self:
            users = self.env['res.users']
            if task.is_shams_todo:
                users = admin_users
                employee = task.owner_employee_id
                if employee and employee.user_id:
                    users |= employee.user_id
                manager = employee.parent_id if employee else self.env['hr.employee']
                while manager:
                    if manager.user_id:
                        users |= manager.user_id
                    manager = manager.parent_id
            task.visibility_user_ids = users

    @api.depends('project_id', 'parent_id')
    def _compute_is_shams_todo(self):
        for task in self:
            task.is_shams_todo = not task.project_id and not task.parent_id

    @api.depends('owner_employee_id', 'owner_employee_id.parent_id')
    def _compute_manager_id(self):
        for task in self:
            task.manager_id = task.owner_employee_id.parent_id

    @api.constrains('actual_hours')
    def _check_actual_hours(self):
        for task in self:
            if task.actual_hours < 0:
                raise ValidationError(_('Actual hours cannot be negative.'))

    @api.constrains('progress')
    def _check_progress(self):
        for task in self:
            if task.progress and (task.progress < 0 or task.progress > 100):
                raise ValidationError(_('Progress must be between 0 and 100.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            is_todo = (
                not vals.get('project_id')
                and not vals.get('parent_id')
            )
            if is_todo:
                employee = self.env.user.employee_id
                if not vals.get('owner_employee_id') and employee:
                    vals['owner_employee_id'] = employee.id
                if not vals.get('user_ids'):
                    vals['user_ids'] = [(4, self.env.uid)]
                vals.setdefault('review_state', 'draft')
        tasks = super().create(vals_list)
        if not self.env.su:
            tasks.filtered(lambda t: not t.project_id and not t.parent_id)._ensure_owner_employee()
        return tasks

    def _ensure_owner_employee(self):
        employee = self.env.user.employee_id
        for task in self:
            if employee and not task.owner_employee_id:
                task.sudo().owner_employee_id = employee.id

    def write(self, vals):
        if not self.env.su:
            protected = {'approved'}
            for task in self.filtered('is_shams_todo'):
                if task.review_state in protected:
                    employee = self.env.user.employee_id
                    is_owner = (
                        employee
                        and task.owner_employee_id == employee
                    )
                    is_admin = self.env.user.has_group(
                        'shams_todo_management.group_shams_todo_admin'
                    )
                    manager_fields = {
                        'review_state', 'reviewed_by', 'reviewed_on', 'review_note',
                    }
                    if is_owner and not is_admin:
                        if set(vals) - manager_fields:
                            raise UserError(_(
                                'Approved to-dos cannot be edited. '
                                'Contact your manager or an administrator.'
                            ))
                    elif not is_admin and not task._can_manage_review():
                        if set(vals) & manager_fields and task.review_state in protected:
                            raise AccessError(_(
                                'You cannot modify review fields on this to-do.'
                            ))
        return super().write(vals)

    def _can_manage_review(self):
        self.ensure_one()
        if not self.is_shams_todo:
            return False
        if self.env.user.has_group('shams_todo_management.group_shams_todo_admin'):
            return True
        employee = self.env.user.employee_id
        if not employee or not self.owner_employee_id:
            return False
        return self._is_in_reporting_tree(employee, self.owner_employee_id)

    def _is_in_reporting_tree(self, manager_employee, owner_employee):
        current = owner_employee.parent_id
        while current:
            if current == manager_employee:
                return True
            current = current.parent_id
        return False

    def _ensure_shams_todo(self):
        self.ensure_one()
        if not self.is_shams_todo:
            raise UserError(_('This action is only available on to-do records.'))

    def _post_review_message(self, body):
        self.message_post(body=body, message_type='notification')

    def action_start(self):
        for task in self:
            task._ensure_shams_todo()
            if task.review_state not in ('draft', 'rejected'):
                raise UserError(_('Only draft or rejected to-dos can be started.'))
            task.review_state = 'in_progress'

    def action_submit_review(self):
        for task in self:
            task._ensure_shams_todo()
            if task.review_state != 'in_progress':
                raise UserError(_('Only in-progress to-dos can be submitted for review.'))
            task.review_state = 'waiting_review'
            task._post_review_message(_('To-do submitted for manager review.'))

    def action_approve(self):
        for task in self:
            task._ensure_shams_todo()
            if not task._can_manage_review():
                raise AccessError(_('You are not allowed to approve this to-do.'))
            if task.review_state != 'waiting_review':
                raise UserError(_('Only to-dos waiting for review can be approved.'))
            task.write({
                'review_state': 'approved',
                'reviewed_by': self.env.uid,
                'reviewed_on': fields.Datetime.now(),
            })
            task._post_review_message(_('To-do approved by %s.', self.env.user.name))

    def action_reject(self):
        for task in self:
            task._ensure_shams_todo()
            if not task._can_manage_review():
                raise AccessError(_('You are not allowed to reject this to-do.'))
            if task.review_state != 'waiting_review':
                raise UserError(_('Only to-dos waiting for review can be rejected.'))
            if not task.review_note:
                raise UserError(_('Please add a review note before rejecting.'))
            task.write({
                'review_state': 'rejected',
                'reviewed_by': self.env.uid,
                'reviewed_on': fields.Datetime.now(),
            })
            task._post_review_message(_(
                'To-do rejected by %s. Review note: %s',
                self.env.user.name,
                task.review_note,
            ))

    def action_cancel(self):
        for task in self:
            task._ensure_shams_todo()
            if task.review_state in ('approved', 'cancelled'):
                raise UserError(_('This to-do cannot be cancelled.'))
            is_owner = (
                task.owner_employee_id.user_id == self.env.user
                or self.env.uid in task.user_ids.ids
            )
            if not is_owner and not task._can_manage_review():
                raise AccessError(_('You are not allowed to cancel this to-do.'))
            task.review_state = 'cancelled'
            task._post_review_message(_('To-do cancelled by %s.', self.env.user.name))

    @api.model
    def action_shams_deduplicate_personal_stages(self):
        """Merge duplicate personal to-do stages for the same user."""
        TaskType = self.env['project.task.type'].sudo()
        PersonalStage = self.env['project.task.stage.personal'].sudo()

        stages_by_key = defaultdict(list)
        for stage in TaskType.search([('user_id', '!=', False)]):
            stages_by_key[(stage.user_id.id, stage.name)].append(stage)

        for stage_list in stages_by_key.values():
            if len(stage_list) <= 1:
                continue
            stage_list.sort(key=lambda stage: (stage.sequence, stage.id))
            keep, *duplicates = stage_list
            duplicate_ids = [stage.id for stage in duplicates]
            PersonalStage.search([('stage_id', 'in', duplicate_ids)]).write({
                'stage_id': keep.id,
            })
            TaskType.browse(duplicate_ids).unlink()

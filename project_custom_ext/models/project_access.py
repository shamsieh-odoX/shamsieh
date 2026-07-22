# -*- coding: utf-8 -*-
from odoo import api, models


class ProjectAccessMixin(models.AbstractModel):
    _name = 'project.custom.access.mixin'
    _description = 'Project Custom Access Helpers'

    def _is_project_admin(self):
        return self.env.user.has_group('project.group_project_manager')

    def _is_custom_manager(self):
        return self.env.user.has_group('project_custom_ext.group_project_custom_manager')

    def _can_create_move(self):
        user = self.env.user
        return (
            self._is_project_admin()
            or self._is_custom_manager()
            or user.has_group('project_custom_ext.group_project_create_move')
        )

    def _is_edit_only(self):
        return (
            self.env.user.has_group('project_custom_ext.group_project_edit_only')
            and not self._can_create_move()
        )

    def _can_move_task_stage(self):
        return self._can_create_move()

    def _can_create_project(self):
        return self._can_create_move()

    @api.model
    def _user_can_create_project(self):
        return self.env['project.custom.access.mixin']._can_create_project()

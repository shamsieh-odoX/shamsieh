# -*- coding: utf-8 -*-

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'shams_todo')
class TestShamsTodoSecurity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Task = cls.env['project.task']

        cls.upper_manager_user = cls.env['res.users'].create({
            'name': 'CEO User',
            'login': 'todo_ceo',
            'email': 'todo_ceo@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('shams_todo_management.group_shams_todo_manager').id,
            ])],
        })
        cls.dept_manager_user = cls.env['res.users'].create({
            'name': 'Department Manager User',
            'login': 'todo_dept_mgr',
            'email': 'todo_dept_mgr@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('shams_todo_management.group_shams_todo_manager').id,
            ])],
        })
        cls.employee_user = cls.env['res.users'].create({
            'name': 'Anton User',
            'login': 'todo_anton',
            'email': 'todo_anton@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('shams_todo_management.group_shams_todo_employee').id,
            ])],
        })
        cls.intruder_user = cls.env['res.users'].create({
            'name': 'Intruder User',
            'login': 'todo_intruder',
            'email': 'todo_intruder@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('shams_todo_management.group_shams_todo_employee').id,
            ])],
        })
        cls.admin_user = cls.env['res.users'].create({
            'name': 'Todo Admin User',
            'login': 'todo_admin',
            'email': 'todo_admin@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('shams_todo_management.group_shams_todo_admin').id,
            ])],
        })

        cls.upper_manager = cls.env['hr.employee'].create({
            'name': 'CEO Employee',
            'user_id': cls.upper_manager_user.id,
        })
        cls.dept_manager = cls.env['hr.employee'].create({
            'name': 'Department Manager Employee',
            'user_id': cls.dept_manager_user.id,
            'parent_id': cls.upper_manager.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Anton Employee',
            'user_id': cls.employee_user.id,
            'parent_id': cls.dept_manager.id,
        })
        cls.intruder = cls.env['hr.employee'].create({
            'name': 'Intruder Employee',
            'user_id': cls.intruder_user.id,
        })

        cls.env.ref('shams_todo_management.group_shams_todo_admin').write({
            'user_ids': [(4, cls.admin_user.id)],
        })

    def _create_todo(self, user, name='Test To-Do'):
        return self.Task.with_user(user).create({
            'name': name,
            'project_id': False,
            'parent_id': False,
            'user_ids': [(4, user.id)],
        })

    def test_employee_sees_only_own_todos(self):
        own = self._create_todo(self.employee_user, 'Anton To-Do')
        intruder_todo = self._create_todo(self.intruder_user, 'Intruder To-Do')

        visible = self.Task.with_user(self.employee_user).search([
            ('id', 'in', [own.id, intruder_todo.id]),
        ])
        self.assertIn(own, visible)
        self.assertNotIn(intruder_todo, visible)

    def test_manager_sees_subordinate_todos(self):
        subordinate_todo = self._create_todo(self.employee_user, 'Team To-Do')

        visible = self.Task.with_user(self.dept_manager_user).search([
            ('id', '=', subordinate_todo.id),
        ])
        self.assertEqual(len(visible), 1)

    def test_upper_manager_sees_full_reporting_tree(self):
        subordinate_todo = self._create_todo(self.employee_user, 'Hierarchy To-Do')

        visible = self.Task.with_user(self.upper_manager_user).search([
            ('id', '=', subordinate_todo.id),
        ])
        self.assertEqual(len(visible), 1)

    def test_intruder_cannot_read_other_employee_todo(self):
        subordinate_todo = self._create_todo(self.employee_user, 'Private To-Do')

        with self.assertRaises(AccessError):
            subordinate_todo.with_user(self.intruder_user).read(['name'])

    def test_owner_employee_auto_filled(self):
        todo = self._create_todo(self.employee_user, 'Auto Owner')
        self.assertEqual(todo.owner_employee_id, self.employee)
        self.assertEqual(todo.manager_id, self.dept_manager)

    def test_workflow_submit_approve(self):
        todo = self._create_todo(self.employee_user, 'Workflow To-Do')
        todo.with_user(self.employee_user).action_start()
        self.assertEqual(todo.review_state, 'in_progress')

        todo.with_user(self.employee_user).action_submit_review()
        self.assertEqual(todo.review_state, 'waiting_review')

        todo.with_user(self.dept_manager_user).action_approve()
        self.assertEqual(todo.review_state, 'approved')
        self.assertEqual(todo.reviewed_by, self.dept_manager_user)
        self.assertTrue(todo.reviewed_on)

    def test_workflow_reject_requires_note(self):
        todo = self._create_todo(self.employee_user, 'Reject To-Do')
        todo.with_user(self.employee_user).action_start()
        todo.with_user(self.employee_user).action_submit_review()

        with self.assertRaises(UserError):
            todo.with_user(self.dept_manager_user).action_reject()

        todo.with_user(self.dept_manager_user).write({'review_note': 'Needs more detail.'})
        todo.with_user(self.dept_manager_user).action_reject()
        self.assertEqual(todo.review_state, 'rejected')
        self.assertIn('Needs more detail', todo.review_note)

    def test_employee_cannot_edit_approved_todo(self):
        todo = self._create_todo(self.employee_user, 'Approved To-Do')
        todo.with_user(self.employee_user).action_start()
        todo.with_user(self.employee_user).action_submit_review()
        todo.with_user(self.dept_manager_user).action_approve()

        with self.assertRaises(UserError):
            todo.with_user(self.employee_user).write({'name': 'Changed'})

    def test_admin_can_access_all_todos(self):
        todo = self._create_todo(self.employee_user, 'Admin Visible')
        visible = self.Task.with_user(self.admin_user).search([
            ('id', '=', todo.id),
        ])
        self.assertEqual(len(visible), 1)

    def test_manager_cannot_access_unrelated_department_todo(self):
        unrelated_todo = self._create_todo(self.intruder_user, 'Unrelated To-Do')

        visible = self.Task.with_user(self.dept_manager_user).search([
            ('id', '=', unrelated_todo.id),
        ])
        self.assertFalse(visible)

        with self.assertRaises(AccessError):
            unrelated_todo.with_user(self.dept_manager_user).read(['name'])

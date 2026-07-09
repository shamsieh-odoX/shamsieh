from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "shams_todo_management")
class TestShamsTodoSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Task = cls.env["project.task"]
        cls.Project = cls.env["project.project"]

        cls.group_employee = cls.env.ref("shams_todo_management.group_shams_todo_employee")
        cls.group_manager = cls.env.ref("shams_todo_management.group_shams_todo_manager")
        cls.group_admin = cls.env.ref("shams_todo_management.group_shams_todo_admin")

        cls.user_employee_a = cls.env["res.users"].create(
            {
                "name": "Todo Employee A",
                "login": "todo_emp_a",
                "email": "todo_emp_a@test.com",
                "group_ids": [(6, 0, [cls.group_employee.id])],
            }
        )
        cls.user_employee_b = cls.env["res.users"].create(
            {
                "name": "Todo Employee B",
                "login": "todo_emp_b",
                "email": "todo_emp_b@test.com",
                "group_ids": [(6, 0, [cls.group_employee.id])],
            }
        )
        cls.user_manager = cls.env["res.users"].create(
            {
                "name": "Todo Manager",
                "login": "todo_manager",
                "email": "todo_manager@test.com",
                "group_ids": [(6, 0, [cls.group_manager.id])],
            }
        )
        cls.user_unrelated_manager = cls.env["res.users"].create(
            {
                "name": "Other Manager",
                "login": "todo_other_manager",
                "email": "todo_other_manager@test.com",
                "group_ids": [(6, 0, [cls.group_manager.id])],
            }
        )
        cls.user_admin = cls.env["res.users"].create(
            {
                "name": "Todo Admin",
                "login": "todo_admin",
                "email": "todo_admin@test.com",
                "group_ids": [(6, 0, [cls.group_admin.id])],
            }
        )

        cls.emp_manager = cls.env["hr.employee"].create(
            {"name": "Manager Emp", "user_id": cls.user_manager.id}
        )
        cls.emp_a = cls.env["hr.employee"].create(
            {"name": "Employee A", "user_id": cls.user_employee_a.id, "parent_id": cls.emp_manager.id}
        )
        cls.emp_b = cls.env["hr.employee"].create(
            {"name": "Employee B", "user_id": cls.user_employee_b.id}
        )
        cls.env["hr.employee"].create(
            {"name": "Other Manager Emp", "user_id": cls.user_unrelated_manager.id}
        )
        cls.env["hr.employee"].create(
            {"name": "Admin Emp", "user_id": cls.user_admin.id}
        )

        cls.project = cls.Project.create({"name": "ToDo Security Project"})
        cls.task_a = cls.Task.create(
            {
                "name": "Employee A Task",
                "project_id": cls.project.id,
                "owner_employee_id": cls.emp_a.id,
            }
        )
        cls.task_b = cls.Task.create(
            {
                "name": "Employee B Task",
                "project_id": cls.project.id,
                "owner_employee_id": cls.emp_b.id,
            }
        )

    def test_employee_sees_only_own_tasks(self):
        tasks = self.Task.with_user(self.user_employee_a).search([])
        self.assertIn(self.task_a, tasks)
        self.assertNotIn(self.task_b, tasks)

    def test_manager_can_see_subordinate_tasks(self):
        tasks = self.Task.with_user(self.user_manager).search([])
        self.assertIn(self.task_a, tasks)

    def test_manager_cannot_see_unrelated_tasks(self):
        tasks = self.Task.with_user(self.user_unrelated_manager).search([])
        self.assertNotIn(self.task_a, tasks)

    def test_admin_can_see_all_tasks(self):
        tasks = self.Task.with_user(self.user_admin).search([])
        self.assertIn(self.task_a, tasks)
        self.assertIn(self.task_b, tasks)

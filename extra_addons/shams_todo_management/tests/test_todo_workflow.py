from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "shams_todo_management")
class TestShamsTodoWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Task = cls.env["project.task"]
        cls.Project = cls.env["project.project"]

        cls.group_employee = cls.env.ref("shams_todo_management.group_shams_todo_employee")
        cls.group_manager = cls.env.ref("shams_todo_management.group_shams_todo_manager")

        cls.user_manager = cls.env["res.users"].create(
            {
                "name": "Workflow Manager",
                "login": "todo_flow_manager",
                "email": "todo_flow_manager@test.com",
                "group_ids": [(6, 0, [cls.group_manager.id])],
            }
        )
        cls.user_employee = cls.env["res.users"].create(
            {
                "name": "Workflow Employee",
                "login": "todo_flow_employee",
                "email": "todo_flow_employee@test.com",
                "group_ids": [(6, 0, [cls.group_employee.id])],
            }
        )
        cls.user_other = cls.env["res.users"].create(
            {
                "name": "Other Employee",
                "login": "todo_flow_other",
                "email": "todo_flow_other@test.com",
                "group_ids": [(6, 0, [cls.group_employee.id])],
            }
        )

        cls.manager_emp = cls.env["hr.employee"].create(
            {"name": "Workflow Manager Emp", "user_id": cls.user_manager.id}
        )
        cls.employee_emp = cls.env["hr.employee"].create(
            {
                "name": "Workflow Employee Emp",
                "user_id": cls.user_employee.id,
                "parent_id": cls.manager_emp.id,
            }
        )
        cls.env["hr.employee"].create(
            {"name": "Workflow Other Emp", "user_id": cls.user_other.id}
        )

        cls.project = cls.Project.create({"name": "ToDo Workflow Project"})

    def test_owner_auto_fill_on_create(self):
        task = self.Task.with_user(self.user_employee).create(
            {"name": "Auto Owner Task", "project_id": self.project.id}
        )
        self.assertEqual(task.owner_employee_id, self.employee_emp)
        self.assertEqual(task.manager_id, self.manager_emp)

    def test_submit_and_approve_workflow(self):
        task = self.Task.with_user(self.user_employee).create(
            {"name": "Approval Flow Task", "project_id": self.project.id}
        )
        task.with_user(self.user_employee).action_start()
        self.assertEqual(task.review_state, "in_progress")

        task.with_user(self.user_employee).action_submit_review()
        self.assertEqual(task.review_state, "waiting_review")

        task.with_user(self.user_manager).action_approve()
        self.assertEqual(task.review_state, "approved")
        self.assertEqual(task.reviewed_by, self.user_manager)
        self.assertTrue(task.reviewed_on)

    def test_only_direct_manager_can_review(self):
        task = self.Task.with_user(self.user_employee).create(
            {"name": "Review Permission Task", "project_id": self.project.id}
        )
        task.with_user(self.user_employee).action_submit_review()
        with self.assertRaises(UserError):
            task.with_user(self.user_other).action_approve()

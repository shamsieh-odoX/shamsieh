from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ProjectTask(models.Model):
    _inherit = "project.task"

    owner_employee_id = fields.Many2one(
        "hr.employee",
        string="Owner Employee",
        index=True,
        tracking=True,
    )
    manager_id = fields.Many2one(
        "hr.employee",
        string="Manager",
        compute="_compute_manager_id",
        store=True,
        index=True,
    )
    review_state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("in_progress", "In Progress"),
            ("waiting_review", "Waiting Review"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        string="Review State",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    estimated_hours = fields.Float(string="Estimated Hours", tracking=True)
    actual_hours = fields.Float(string="Actual Hours", tracking=True)
    progress = fields.Integer(string="Progress (%)", default=0, tracking=True)
    work_done = fields.Html(string="Work Done")
    what_learned = fields.Html(string="What Learned")
    blockers = fields.Html(string="Blockers")
    tomorrow_plan = fields.Html(string="Tomorrow Plan")
    reviewed_by = fields.Many2one("res.users", string="Reviewed By", readonly=True, copy=False)
    reviewed_on = fields.Datetime(string="Reviewed On", readonly=True, copy=False)
    review_note = fields.Html(string="Review Note", copy=False)
    can_review = fields.Boolean(compute="_compute_can_review")

    @api.depends("owner_employee_id", "owner_employee_id.parent_id")
    def _compute_manager_id(self):
        for record in self:
            record.manager_id = record.owner_employee_id.parent_id

    @api.depends_context("uid")
    @api.depends("owner_employee_id", "manager_id")
    def _compute_can_review(self):
        employee = self.env.user.employee_id
        for record in self:
            record.can_review = bool(
                employee
                and record.owner_employee_id
                and record.owner_employee_id.parent_id == employee
            )

    @api.constrains("progress")
    def _check_progress_range(self):
        for record in self:
            if record.progress < 0 or record.progress > 100:
                raise ValidationError(_("Progress must be between 0 and 100."))

    @api.constrains("actual_hours", "estimated_hours")
    def _check_hours_non_negative(self):
        for record in self:
            if record.actual_hours < 0 or record.estimated_hours < 0:
                raise ValidationError(_("Estimated and actual hours cannot be negative."))

    @api.model_create_multi
    def create(self, vals_list):
        employee = self.env.user.employee_id
        for vals in vals_list:
            if not vals.get("owner_employee_id") and employee:
                vals["owner_employee_id"] = employee.id
            if vals.get("owner_employee_id") and not vals.get("user_ids"):
                owner = self.env["hr.employee"].browse(vals["owner_employee_id"])
                if owner.user_id:
                    vals["user_ids"] = [(6, 0, [owner.user_id.id])]
        records = super().create(vals_list)
        return records

    def write(self, vals):
        if "owner_employee_id" in vals and not self.env.user.has_group("shams_todo_management.group_shams_todo_admin"):
            raise UserError(_("Only To-Do admins can change task ownership."))

        restricted_fields = {
            "name",
            "description",
            "date_deadline",
            "priority",
            "estimated_hours",
            "actual_hours",
            "progress",
            "work_done",
            "what_learned",
            "blockers",
            "tomorrow_plan",
        }
        if restricted_fields & set(vals):
            current_employee = self.env.user.employee_id
            for record in self:
                if record.review_state == "approved" and record.owner_employee_id == current_employee and not self.env.user.has_group(
                    "shams_todo_management.group_shams_todo_admin"
                ):
                    raise UserError(_("Approved tasks cannot be edited by the owner unless reset by a manager/admin."))
        return super().write(vals)

    def _ensure_owner(self):
        owner_records = self.filtered(lambda rec: rec.owner_employee_id == self.env.user.employee_id)
        if len(owner_records) != len(self):
            raise UserError(_("Only task owner can perform this action."))

    def _ensure_reviewer(self):
        if self.env.user.has_group("shams_todo_management.group_shams_todo_admin"):
            return
        employee = self.env.user.employee_id
        for record in self:
            if not employee or record.owner_employee_id.parent_id != employee:
                raise UserError(_("Only the direct manager can review this task."))

    def _post_state_message(self, message):
        for record in self:
            if hasattr(record, "message_post"):
                record.message_post(body=message)

    def action_start(self):
        self._ensure_owner()
        self.write({"review_state": "in_progress"})
        self._post_state_message(_("Task moved to In Progress."))
        return True

    def action_submit_review(self):
        self._ensure_owner()
        self.write({"review_state": "waiting_review"})
        self._post_state_message(_("Task submitted for manager review."))
        return True

    def action_approve(self):
        self._ensure_reviewer()
        self.write(
            {
                "review_state": "approved",
                "reviewed_by": self.env.user.id,
                "reviewed_on": fields.Datetime.now(),
            }
        )
        self._post_state_message(_("Task approved by manager."))
        return True

    def action_reject(self):
        self._ensure_reviewer()
        self.write(
            {
                "review_state": "rejected",
                "reviewed_by": self.env.user.id,
                "reviewed_on": fields.Datetime.now(),
            }
        )
        self._post_state_message(_("Task rejected and returned for changes."))
        return True

    def action_cancel(self):
        self.write({"review_state": "cancelled"})
        self._post_state_message(_("Task cancelled."))
        return True

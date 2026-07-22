# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class HrOvertimeApprovalLine(models.Model):
    _name = 'hr.overtime.approval.line'
    _description = 'Overtime Approval Line'
    _order = 'sequence, id'

    request_id = fields.Many2one(
        'hr.overtime.request',
        string='Overtime Request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(default=10)
    role = fields.Selection(
        selection=[
            ('dept_manager', 'Department Manager'),
            ('upper_manager', 'Upper Manager'),
            ('hr', 'HR Officer'),
        ],
        required=True,
    )
    approver_id = fields.Many2one('res.users', string='Approver', required=True)
    state = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('to_approve', 'To Approve'),
            ('approved', 'Approved'),
            ('refused', 'Refused'),
        ],
        string='Status',
        default='pending',
        required=True,
    )
    decision_date = fields.Datetime(string='Decision Date')
    comment = fields.Text(string='Comment')

    role_label = fields.Char(compute='_compute_role_label')

    @api.depends('role')
    def _compute_role_label(self):
        selection = dict(self._fields['role'].selection)
        for line in self:
            line.role_label = selection.get(line.role, line.role)

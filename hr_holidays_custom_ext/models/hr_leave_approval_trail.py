# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class HrLeaveApprovalTrail(models.Model):
    _name = 'hr.leave.approval.trail'
    _description = 'Leave Approval Trail'
    _order = 'sequence, id'

    leave_id = fields.Many2one(
        'hr.leave',
        string='Time Off Request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(default=10)
    stage = fields.Selection(
        selection=[
            ('submitted', 'Submitted'),
            ('first_approval', 'First Approval'),
            ('second_approval', 'Second Approval'),
            ('refused', 'Refused'),
            ('cancelled', 'Cancelled'),
        ],
        required=True,
    )
    approver_id = fields.Many2one('hr.employee', string='Approver')
    state = fields.Selection(
        selection=[
            ('submitted', 'Submitted'),
            ('approved', 'Approved'),
            ('refused', 'Refused'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        required=True,
    )
    decision_date = fields.Datetime(string='Decision Date', default=fields.Datetime.now)
    comment = fields.Text(string='Comment')
    stage_label = fields.Char(compute='_compute_stage_label')

    @api.depends('stage')
    def _compute_stage_label(self):
        selection = dict(self._fields['stage'].selection)
        for line in self:
            line.stage_label = selection.get(line.stage, line.stage)

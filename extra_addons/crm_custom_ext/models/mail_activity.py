# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    @api.model_create_multi
    def create(self, vals_list):
        activities = super().create(vals_list)
        activities._update_crm_lead_dates()
        return activities

    def write(self, vals):
        result = super().write(vals)
        if 'date_deadline' in vals:
            self._update_crm_lead_dates()
        return result

    def _update_crm_lead_dates(self):
        leads = self.env['crm.lead']
        for activity in self:
            if activity.res_model == 'crm.lead' and activity.res_id:
                leads |= self.env['crm.lead'].browse(activity.res_id)
        if leads:
            leads._sync_next_followup_from_activities()

    def _action_done(self, feedback=False, attachment_ids=None):
        leads = self.env['crm.lead']
        for activity in self:
            if activity.res_model == 'crm.lead' and activity.res_id:
                leads |= self.env['crm.lead'].browse(activity.res_id)
        activities = super()._action_done(feedback=feedback, attachment_ids=attachment_ids)
        if leads:
            leads.write({'last_contact_date': fields.Date.context_today(self)})
            leads._sync_next_followup_from_activities()
        return activities

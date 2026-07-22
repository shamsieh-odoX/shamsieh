# -*- coding: utf-8 -*-

from odoo import fields, models


class WebsiteLeadSubmissionLog(models.Model):
    _name = 'website.lead.submission.log'
    _description = 'Website Lead API Submission Log'
    _order = 'create_date desc'

    ip_address = fields.Char(required=True, index=True)
    email = fields.Char()
    lead_id = fields.Many2one('crm.lead', ondelete='set null')

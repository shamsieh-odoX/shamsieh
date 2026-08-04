# -*- coding: utf-8 -*-

from odoo import fields, models

SERVICE_INTEREST_SELECTION = [
    ('implementation', 'ERP Implementation'),
    ('customization', 'Custom Development'),
    ('migration', 'Data Migration'),
    ('integration', 'System Integration'),
    ('support', 'Technical Support'),
    ('training', 'Training & Documentation'),
    ('ai', 'AI & Automation'),
    ('other', 'Other'),
]

PREFERRED_CONTACT_METHOD_SELECTION = [
    ('email', 'Email'),
    ('phone', 'Phone'),
    ('either', 'Either'),
]


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    service_interest = fields.Selection(
        SERVICE_INTEREST_SELECTION,
        string='Service Interest',
        tracking=True,
        index=True,
    )
    preferred_contact_method = fields.Selection(
        PREFERRED_CONTACT_METHOD_SELECTION,
        string='Preferred Contact Method',
        tracking=True,
    )

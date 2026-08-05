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

WEBSITE_SITE_SELECTION = [
    ('shamsieh', 'Shamsieh'),
    ('aiodyx', 'AIODYX'),
]

WEBSITE_FORM_TYPE_SELECTION = [
    ('contact', 'Contact'),
    ('product_demo', 'Product Demo'),
    ('consultation', 'Consultation'),
    ('other', 'Other'),
]

WEBSITE_PRODUCT_SELECTION = [
    ('botify_ai', 'Botify AI'),
    ('safa_ai', 'Safa AI Assistant'),
    ('mawid', 'Mawid'),
    ('shamsieh_education', 'Shamsieh Education'),
    ('aiodyx_erp', 'AIODYX ERP'),
    ('other', 'Other'),
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
    website_site = fields.Selection(
        WEBSITE_SITE_SELECTION,
        string='Website',
        tracking=True,
        index=True,
        help='External website that submitted this lead.',
    )
    website_form_type = fields.Selection(
        WEBSITE_FORM_TYPE_SELECTION,
        string='Website Form',
        tracking=True,
        index=True,
        help='Which website form created this lead (contact, product demo, etc.).',
    )
    website_product = fields.Selection(
        WEBSITE_PRODUCT_SELECTION,
        string='Website Product',
        tracking=True,
        index=True,
        help='Product related to a demo or product-page inquiry.',
    )
    website_subject = fields.Char(
        string='Website Subject',
        tracking=True,
        help='Subject line sent by the website form.',
    )

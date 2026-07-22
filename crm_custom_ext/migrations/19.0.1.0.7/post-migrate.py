# -*- coding: utf-8 -*-
"""Force Arabic labels on CRM stages (including manually created ones)."""

STAGE_AR = {
    'Scope of Work': 'نطاق العمل',
    'Scope Of Work': 'نطاق العمل',
    'Contract': 'العقد',
    'Lost': 'ضائع',
    'Qualified': 'مؤهل',
    'Demo Scheduled': 'عرض توضيحي مجدول',
    'Demo Completed': 'اكتمال العرض التوضيحي',
    'Negotiation': 'التفاوض',
    'Pending Decision': 'بانتظار القرار',
    'Follow-up Required': 'يتطلب متابعة',
    'On Hold': 'معلّق',
    'New Lead': 'عميل مهتم جديد',
    'Contacted': 'تم التواصل',
    'Proposal Sent': 'تم إرسال العرض',
    'Won': 'تم الفوز',
}


def _arabic_lang_code(env):
    Lang = env['res.lang'].with_context(active_test=False)
    for code in ('ar_001', 'ar_SY', 'ar'):
        if Lang._lang_get(code):
            return code
    lang = Lang.search([('iso_code', '=', 'ar')], limit=1)
    return lang.code if lang else None


def migrate(cr, version):
    from odoo.api import Environment

    env = Environment(cr, 1, {})
    lang = _arabic_lang_code(env)
    if not lang:
        return

    Stage = env['crm.stage'].with_context(active_test=False, lang='en_US')
    for en_name, ar_name in STAGE_AR.items():
        stages = Stage.search([('name', '=ilike', en_name)])
        for stage in stages:
            stage.update_field_translations('name', {lang: ar_name})

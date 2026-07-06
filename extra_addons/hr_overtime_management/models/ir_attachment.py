# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    def _is_overtime_attachment_vals(self, vals):
        if vals.get('res_model') == 'hr.overtime.request':
            return True
        return self.env.context.get('default_res_model') == 'hr.overtime.request'

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            if self._is_overtime_attachment_vals(vals):
                vals['company_id'] = False
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        if self.filtered(lambda att: att.res_model == 'hr.overtime.request'):
            vals = dict(vals)
            if 'company_id' not in vals:
                vals['company_id'] = False
        return super().write(vals)

# -*- coding: utf-8 -*-

import base64

from odoo import _, fields, models
from odoo.exceptions import UserError

from odoo.addons.hr_attendance_custom_ext.services.face_provider import get_face_provider
from odoo.addons.hr_attendance_custom_ext.services.face_provider_insightface import (
    FaceProviderUnavailable,
    UNAVAILABLE_MESSAGE,
)


class HrEmployeeFaceEnrollWizard(models.TransientModel):
    _name = 'hr.employee.face.enroll.wizard'
    _description = 'Enroll Employee Face Template'

    employee_id = fields.Many2one('hr.employee', required=True)
    company_id = fields.Many2one(related='employee_id.company_id')
    enrollment_image = fields.Binary(string='Enrollment Image', required=True, attachment=False)
    enrollment_image_filename = fields.Char()
    notes = fields.Text()

    def action_enroll(self):
        self.ensure_one()
        employee = self.employee_id
        company = employee.company_id
        if not self.enrollment_image:
            raise UserError(_('Enrollment image is required.'))

        try:
            provider = get_face_provider(company)
            if not provider.is_available():
                raise FaceProviderUnavailable(UNAVAILABLE_MESSAGE)
            image_bytes = base64.b64decode(self.enrollment_image)
            embedding = provider.extract_embedding(image_bytes)
        except FaceProviderUnavailable as exc:
            raise UserError(_(
                '%(message)s Install optional Python packages from requirements-face.txt.',
                message=str(exc),
            )) from exc
        except ValueError as exc:
            raise UserError(str(exc)) from exc

        Template = self.env['hr.employee.face.template']
        employee.face_template_ids.filtered('active').write({'active': False})

        template_vals = {
            'employee_id': employee.id,
            'provider': company.face_provider or 'insightface',
            'active': True,
            'enrolled_at': fields.Datetime.now(),
            'enrolled_by': self.env.user.id,
            'notes': self.notes,
        }
        template = Template.create(template_vals)
        template.set_embedding_vector(embedding)
        template.deactivate_others_for_employee()

        if company.face_store_raw_images:
            attachment = self.env['ir.attachment'].create({
                'name': self.enrollment_image_filename or f'face-enrollment-{employee.id}.jpg',
                'type': 'binary',
                'datas': self.enrollment_image,
                'res_model': 'hr.employee.face.template',
                'res_id': template.id,
                'mimetype': 'image/jpeg',
            })
            template.image_attachment_id = attachment.id

        employee.write({
            'face_enrollment_status': 'enrolled',
            'face_enrolled_at': fields.Datetime.now(),
            'face_enrolled_by': self.env.user.id,
            'face_template_id': str(template.id),
        })
        return {'type': 'ir.actions.act_window_close'}

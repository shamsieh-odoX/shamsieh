"""Purge leftover payroll settings view from the removed glue module."""


def migrate(cr, version):
    cr.execute(
        """
        DELETE FROM ir_ui_view
         WHERE name = 'res.config.settings.view.form.overtime.payroll'
            OR arch_db::text LIKE '%overtime_payroll_setting%'
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = 'hr_overtime_payroll'
           AND model = 'ir.ui.view'
           AND name IN (
                'res_config_settings_view_form_overtime_payroll'
           )
        """
    )

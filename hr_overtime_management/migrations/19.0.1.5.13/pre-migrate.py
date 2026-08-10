"""Remove orphaned payroll settings view that breaks overtime upgrade.

hr_overtime_payroll used to inherit overtime settings with:
  xpath //setting[@id='overtime_payroll_setting']
That setting was removed from overtime, but the child view can remain in the
DB and fails validation when overtime settings are reloaded.
"""


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
           AND name = 'res_config_settings_view_form_overtime_payroll'
           AND model = 'ir.ui.view'
        """
    )

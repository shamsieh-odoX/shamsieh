# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date

from freezegun import freeze_time

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'hr_holidays_custom_ext')
class TestSickLeaveRenewal(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({
            'name': 'Sick Renewal Test Co',
            'sick_leave_days_per_year': 14,
        })
        cls.RenewalLog = cls.env['hr.sick.leave.renewal.log']
        cls.Allocation = cls.env['hr.leave.allocation'].sudo()

        cls.sick_type = cls.env.ref(
            'hr_holidays_custom_ext.leave_type_sick_leave',
            raise_if_not_found=False,
        )
        if not cls.sick_type:
            cls.sick_type = cls.env['hr.leave.type'].create({
                'name': 'Sick Leave',
                'requires_allocation': True,
                'allocation_validation_type': 'no_validation',
                'leave_validation_type': 'hr',
                'request_unit': 'day',
                'company_id': False,
            })

        standard_sick = cls.env.ref('hr_holidays.leave_type_sick_time_off', raise_if_not_found=False)
        if standard_sick:
            standard_sick.active = False

        cls.active_employee = cls.env['hr.employee'].create({
            'name': 'Active Sick Leave Employee',
            'company_id': cls.company.id,
        })
        cls.inactive_employee = cls.env['hr.employee'].create({
            'name': 'Inactive Sick Leave Employee',
            'company_id': cls.company.id,
            'active': False,
        })

    def _allocation_count(self, employee):
        return self.Allocation.search_count([
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', self.sick_type.id),
            ('date_from', '=', date(2026, 1, 1)),
        ])

    @freeze_time('2026-01-01 08:00:00')
    def test_jan_1_creates_allocation(self):
        logs = self.RenewalLog._run_renewal(
            company=self.company,
            year=2026,
            trigger='cron',
            force=False,
        )
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs.allocations_created, 1)
        self.assertEqual(logs.employees_processed, 1)
        self.assertEqual(self._allocation_count(self.active_employee), 1)
        allocation = self.Allocation.search([
            ('employee_id', '=', self.active_employee.id),
            ('holiday_status_id', '=', self.sick_type.id),
            ('date_from', '=', date(2026, 1, 1)),
        ], limit=1)
        self.assertEqual(allocation.state, 'validate')
        self.assertEqual(allocation.number_of_days, 14)

    @freeze_time('2026-01-01 08:00:00')
    def test_rerun_same_year_no_duplicate(self):
        self.RenewalLog._run_renewal(company=self.company, year=2026, trigger='cron', force=False)
        logs = self.RenewalLog._run_renewal(company=self.company, year=2026, trigger='cron', force=False)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs.allocations_created, 0)
        self.assertEqual(logs.allocations_skipped, 1)
        self.assertEqual(self._allocation_count(self.active_employee), 1)

    @freeze_time('2026-01-01 08:00:00')
    def test_inactive_employee_skipped(self):
        logs = self.RenewalLog._run_renewal(
            company=self.company,
            year=2026,
            trigger='cron',
            force=False,
        )
        self.assertEqual(logs.employees_processed, 1)
        self.assertEqual(self._allocation_count(self.inactive_employee), 0)

    @freeze_time('2026-06-15 08:00:00')
    def test_manual_run_works_off_jan_1(self):
        logs = self.RenewalLog._run_renewal(
            company=self.company,
            year=2026,
            trigger='manual',
            force=True,
        )
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs.allocations_created, 1)
        self.assertEqual(self._allocation_count(self.active_employee), 1)

    def test_standard_sick_time_off_deactivated(self):
        standard_sick = self.env.ref('hr_holidays.leave_type_sick_time_off', raise_if_not_found=False)
        if standard_sick:
            standard_sick.invalidate_recordset()
            self.assertFalse(standard_sick.active)

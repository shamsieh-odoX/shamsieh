# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date

from freezegun import freeze_time

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools.float_utils import float_compare


@tagged('post_install', '-at_install', 'hr_holidays_custom_ext')
class TestHourlyDeparture(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({
            'name': 'Hourly Departure Test Co',
            'hourly_departure_max_hours_day': 3.0,
            'hourly_departure_max_hours_month': 6.0,
        })
        cls.Leave = cls.env['hr.leave'].sudo()
        cls.Allocation = cls.env['hr.leave.allocation'].sudo()
        cls.Balance = cls.env['hr.hourly.departure.balance'].sudo()
        cls.Conversion = cls.env['hr.hourly.departure.conversion'].sudo()
        cls.AllocationLog = cls.env['hr.hourly.departure.allocation.log'].sudo()

        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'Departure Test Calendar',
            'tz': 'Asia/Riyadh',
            'hours_per_day': 8.0,
            'attendance_ids': [
                (0, 0, {
                    'name': 'Morning',
                    'dayofweek': str(day),
                    'hour_from': 8.0,
                    'hour_to': 12.0,
                    'day_period': 'morning',
                })
                for day in range(5)
            ] + [
                (0, 0, {
                    'name': 'Afternoon',
                    'dayofweek': str(day),
                    'hour_from': 13.0,
                    'hour_to': 17.0,
                    'day_period': 'afternoon',
                })
                for day in range(5)
            ],
        })
        cls.company.resource_calendar_id = cls.calendar.id

        cls.manager_user = cls.env['res.users'].create({
            'name': 'Departure Manager',
            'login': 'departure_mgr_test',
            'email': 'departure_mgr_test@test.com',
            'group_ids': [(6, 0, [
                cls.env.ref('hr_holidays.group_hr_holidays_user').id,
                cls.env.ref('base.group_user').id,
            ])],
        })
        cls.manager_employee = cls.env['hr.employee'].create({
            'name': 'Departure Manager Emp',
            'user_id': cls.manager_user.id,
            'company_id': cls.company.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Departure Employee',
            'company_id': cls.company.id,
            'resource_calendar_id': cls.calendar.id,
            'leave_manager_id': cls.manager_user.id,
            'parent_id': cls.manager_employee.id,
        })

        cls.departure_type = cls.env['hr.leave.type'].create({
            'name': 'Hourly Departure Test',
            'requires_allocation': False,
            'leave_validation_type': 'manager',
            'request_unit': 'hour',
            'is_hourly_departure': True,
            'company_id': cls.company.id,
        })
        cls.annual_type = cls.env['hr.leave.type'].create({
            'name': 'Annual Leave Departure Test',
            'requires_allocation': True,
            'allocation_validation_type': 'no_validation',
            'leave_validation_type': 'no_validation',
            'request_unit': 'day',
            'company_id': cls.company.id,
        })
        cls.company.hourly_departure_type_id = cls.departure_type.id
        cls.company.annual_leave_type_id = cls.annual_type.id

        annual_allocation = cls.Allocation.create({
            'name': 'Annual 2026',
            'employee_id': cls.employee.id,
            'holiday_status_id': cls.annual_type.id,
            'allocation_type': 'regular',
            'number_of_days': 21,
            'date_from': date(2026, 1, 1),
            'date_to': date(2026, 12, 31),
        })
        if annual_allocation.state != 'validate':
            annual_allocation.action_approve()

    def _create_departure(self, day, hour_from, hour_to, reason='Special reason', approve=False):
        leave = self.Leave.create({
            'name': 'Hourly departure',
            'departure_reason': reason,
            'employee_id': self.employee.id,
            'holiday_status_id': self.departure_type.id,
            'request_date_from': day,
            'request_date_to': day,
            'request_unit_hours': True,
            'request_hour_from': hour_from,
            'request_hour_to': hour_to,
        })
        if approve:
            leave.with_user(self.manager_user).action_approve()
        return leave

    def test_rejects_single_request_over_daily_cap(self):
        with self.assertRaises(ValidationError):
            # 8:00-11:30 = 3.5 hours
            self._create_departure(date(2026, 8, 10), 8.0, 11.5)

    def test_rejects_day_total_over_cap_across_requests(self):
        first = self._create_departure(date(2026, 8, 10), 8.0, 10.0)  # 2h
        self.assertTrue(float_compare(first.number_of_hours, 2.0, precision_digits=2) == 0)
        with self.assertRaises(ValidationError):
            self._create_departure(date(2026, 8, 10), 13.0, 15.5)  # +2.5h => 4.5

    def test_rejects_month_total_over_cap(self):
        self._create_departure(date(2026, 8, 10), 8.0, 11.0)  # 3h
        self._create_departure(date(2026, 8, 11), 8.0, 11.0)  # 3h
        with self.assertRaises(ValidationError):
            self._create_departure(date(2026, 8, 12), 8.0, 9.0)  # +1h => 7h

    def test_allows_three_plus_three_on_different_days(self):
        first = self._create_departure(date(2026, 8, 10), 8.0, 11.0)
        second = self._create_departure(date(2026, 8, 11), 8.0, 11.0)
        self.assertEqual(first.state, 'confirm')
        self.assertEqual(second.state, 'confirm')
        self.assertTrue(float_compare(first.number_of_hours, 3.0, precision_digits=2) == 0)
        self.assertTrue(float_compare(second.number_of_hours, 3.0, precision_digits=2) == 0)

    def test_requires_departure_reason(self):
        with self.assertRaises(ValidationError):
            self.Leave.create({
                'name': 'Hourly departure',
                'departure_reason': '   ',
                'employee_id': self.employee.id,
                'holiday_status_id': self.departure_type.id,
                'request_date_from': date(2026, 8, 10),
                'request_date_to': date(2026, 8, 10),
                'request_unit_hours': True,
                'request_hour_from': 8.0,
                'request_hour_to': 10.0,
            })

    def test_accumulation_converts_to_annual_leave(self):
        # 3h + 3h + 2h across months = 8h work day
        self._create_departure(date(2026, 8, 10), 8.0, 11.0, approve=True)
        self._create_departure(date(2026, 8, 11), 8.0, 11.0, approve=True)
        self._create_departure(date(2026, 9, 7), 8.0, 10.0, approve=True)

        balance = self.Balance.search([('employee_id', '=', self.employee.id)], limit=1)
        self.assertTrue(balance)
        self.assertTrue(float_compare(balance.accumulated_hours, 0.0, precision_digits=2) == 0)

        conversions = self.Conversion.search([
            ('employee_id', '=', self.employee.id),
            ('state', '=', 'done'),
        ])
        self.assertEqual(len(conversions), 1)
        self.assertEqual(conversions.annual_leave_id.state, 'validate')
        self.assertTrue(conversions.annual_leave_id.is_hourly_departure_conversion)
        self.assertEqual(conversions.annual_leave_id.number_of_days, 1.0)

    @freeze_time('2026-08-01 08:00:00')
    def test_monthly_allocation_cron_creates_six_hours(self):
        self.departure_type.requires_allocation = True
        logs = self.AllocationLog._run_allocation(
            company=self.company,
            year=2026,
            month=8,
            trigger='cron',
            force=False,
        )
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs.allocations_created, 1)
        allocation = self.Allocation.search([
            ('employee_id', '=', self.employee.id),
            ('holiday_status_id', '=', self.departure_type.id),
            ('allocation_origin', '=', 'hourly_departure_monthly'),
            ('origin_year', '=', 2026),
            ('origin_month', '=', 8),
        ], limit=1)
        self.assertTrue(allocation)
        self.assertEqual(allocation.state, 'validate')
        self.assertTrue(float_compare(allocation.number_of_days, 0.75, precision_digits=2) == 0)

    @freeze_time('2026-08-01 08:00:00')
    def test_monthly_allocation_no_duplicate(self):
        self.departure_type.requires_allocation = True
        self.AllocationLog._run_allocation(
            company=self.company, year=2026, month=8, trigger='manual', force=True,
        )
        logs = self.AllocationLog._run_allocation(
            company=self.company, year=2026, month=8, trigger='manual', force=True,
        )
        self.assertEqual(logs.allocations_created, 0)
        self.assertEqual(logs.allocations_skipped, 1)

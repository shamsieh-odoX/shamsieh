# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date, timedelta

from freezegun import freeze_time

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'hr_holidays_custom_ext')
class TestAnnualLeaveCarryover(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({
            'name': 'Annual Carryover Test Co',
            'annual_leave_days_per_year': 21,
        })
        cls.CarryoverLog = cls.env['hr.annual.leave.carryover.log']
        cls.BalanceSummary = cls.env['hr.leave.balance.summary']
        cls.Allocation = cls.env['hr.leave.allocation'].sudo()
        cls.Leave = cls.env['hr.leave'].sudo()

        cls.annual_type = cls.env['hr.leave.type'].create({
            'name': 'Annual Leave Test',
            'requires_allocation': True,
            'allocation_validation_type': 'no_validation',
            'leave_validation_type': 'hr',
            'request_unit': 'day',
            'company_id': cls.company.id,
        })
        cls.company.annual_leave_type_id = cls.annual_type.id

        cls.employee = cls.env['hr.employee'].create({
            'name': 'Annual Leave Employee',
            'company_id': cls.company.id,
        })

    def _create_allocation(self, origin, origin_year, days, expiring=0.0, expiration=False):
        allocation = self.Allocation.create({
            'name': f'{origin} {origin_year}',
            'employee_id': self.employee.id,
            'holiday_status_id': self.annual_type.id,
            'allocation_type': 'regular',
            'allocation_origin': origin,
            'origin_year': origin_year,
            'number_of_days': days,
            'expiring_carryover_days': expiring,
            'carried_over_days_expiration_date': expiration,
            'date_from': date(origin_year, 1, 1),
            'date_to': date(origin_year, 12, 31),
        })
        if allocation.state != 'validate':
            allocation.action_approve()
        return allocation

    def _create_leave(self, days, start_date):
        end_date = start_date + timedelta(days=days - 1)
        leave = self.Leave.create({
            'name': 'Annual Leave',
            'employee_id': self.employee.id,
            'holiday_status_id': self.annual_type.id,
            'request_date_from': start_date,
            'request_date_to': end_date,
            'number_of_days': days,
        })
        leave.action_approve()
        return leave

    def _carryover_allocation(self, origin_year, origin):
        return self.Allocation.search([
            ('employee_id', '=', self.employee.id),
            ('holiday_status_id', '=', self.annual_type.id),
            ('allocation_origin', '=', origin),
            ('origin_year', '=', origin_year),
            ('date_from', '=', date(origin_year, 1, 1)),
        ], limit=1)

    @freeze_time('2027-01-01 08:00:00')
    def test_unused_balance_gets_carryover(self):
        self._create_allocation('annual_grant', 2026, 21)
        self._create_leave(5, date(2026, 6, 1))
        expected_row = self.BalanceSummary._get_balance_row(
            self.employee,
            self.annual_type,
            date(2026, 12, 31),
        )
        self.assertGreater(expected_row['current_year_balance'], 0)

        logs = self.CarryoverLog._run_carryover(
            company=self.company,
            target_year=2027,
            trigger='manual',
            force=True,
        )
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs.carryovers_created, 1)

        carryover = self._carryover_allocation(2027, 'year_carryover')
        self.assertTrue(carryover)
        self.assertEqual(carryover.number_of_days, expected_row['current_year_balance'])
        self.assertEqual(carryover.expiring_carryover_days, expected_row['current_year_balance'])
        self.assertEqual(carryover.carried_over_days_expiration_date, date(2027, 12, 31))

        grant = self._carryover_allocation(2027, 'annual_grant')
        self.assertTrue(grant)
        self.assertEqual(grant.number_of_days, 21.0)

    def _consume_current_year_balance(self, as_of_date):
        start = date(as_of_date.year, 1, 5)
        for _ in range(10):
            balance_row = self.BalanceSummary._get_balance_row(
                self.employee,
                self.annual_type,
                as_of_date,
            )
            remaining = balance_row['current_year_balance']
            if remaining <= 0:
                return balance_row
            self._create_leave(min(5.0, remaining), start)
            start += timedelta(days=14)
        return self.BalanceSummary._get_balance_row(
            self.employee,
            self.annual_type,
            as_of_date,
        )

    @freeze_time('2027-01-01 08:00:00')
    def test_zero_current_year_balance_no_carryover(self):
        self._create_allocation('annual_grant', 2026, 21)
        balance_row = self._consume_current_year_balance(date(2026, 12, 31))
        self.assertEqual(balance_row['current_year_balance'], 0)

        logs = self.CarryoverLog._run_carryover(
            company=self.company,
            target_year=2027,
            trigger='manual',
            force=True,
        )
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs.carryovers_created, 0)
        self.assertEqual(logs.grants_created, 1)
        self.assertFalse(self._carryover_allocation(2027, 'year_carryover'))

    @freeze_time('2027-01-01 08:00:00')
    def test_rerun_same_year_no_duplicate(self):
        self._create_allocation('annual_grant', 2026, 21)
        self._create_leave(5, date(2026, 6, 1))

        self.CarryoverLog._run_carryover(
            company=self.company,
            target_year=2027,
            trigger='manual',
            force=True,
        )
        allocation_count = self.Allocation.search_count([
            ('employee_id', '=', self.employee.id),
            ('holiday_status_id', '=', self.annual_type.id),
            ('origin_year', '=', 2027),
        ])
        logs = self.CarryoverLog._run_carryover(
            company=self.company,
            target_year=2027,
            trigger='manual',
            force=True,
        )
        self.assertEqual(logs.grants_skipped, 1)
        self.assertEqual(logs.carryovers_skipped, 1)
        self.assertEqual(self.Allocation.search_count([
            ('employee_id', '=', self.employee.id),
            ('holiday_status_id', '=', self.annual_type.id),
            ('origin_year', '=', 2027),
        ]), allocation_count)

    @freeze_time('2027-01-01 08:00:00')
    def test_expired_carryover_forfeited(self):
        self._create_allocation(
            'year_carryover',
            2026,
            10,
            expiring=10.0,
            expiration=date(2026, 12, 31),
        )

        logs = self.CarryoverLog._run_carryover(
            company=self.company,
            target_year=2027,
            trigger='manual',
            force=True,
        )
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs.carryover_days_forfeited, 10.0)

        expired = self.Allocation.search([
            ('employee_id', '=', self.employee.id),
            ('holiday_status_id', '=', self.annual_type.id),
            ('allocation_origin', '=', 'year_carryover'),
            ('origin_year', '=', 2026),
            ('state', '=', 'refuse'),
        ], limit=1)
        self.assertTrue(expired)

    def test_balance_helper_matches_summary(self):
        self._create_allocation('annual_grant', 2026, 21)
        self._create_leave(5, date(2026, 6, 1))
        as_of_date = date(2026, 12, 31)

        helper_row = self.BalanceSummary._get_balance_row(
            self.employee,
            self.annual_type,
            as_of_date,
        )
        summary_rows = self.BalanceSummary._collect_balance_rows(
            as_of_date=as_of_date,
            company_id=self.company.id,
            leave_type_id=self.annual_type.id,
        )
        self.assertEqual(len(summary_rows), 1)
        summary_row = summary_rows[0]
        for key in (
            'employee_id',
            'leave_type_id',
            'company_id',
            'as_of_date',
            'total_accrued',
            'days_used',
            'days_remaining',
            'carried_over',
            'current_year_balance',
            'total_available',
        ):
            self.assertEqual(helper_row[key], summary_row[key], msg=key)
        self.assertGreater(helper_row['current_year_balance'], 0)

    @freeze_time('2027-01-01 08:00:00')
    def test_carryover_respects_company_cap(self):
        self.company.annual_leave_carryover_max_days = 5
        self._create_allocation('annual_grant', 2026, 21)
        self._create_leave(5, date(2026, 6, 1))
        balance_row = self.BalanceSummary._get_balance_row(
            self.employee,
            self.annual_type,
            date(2026, 12, 31),
        )
        raw_carryover = balance_row['current_year_balance']
        expected_capped = max(0.0, raw_carryover - 5.0)

        logs = self.CarryoverLog._run_carryover(
            company=self.company,
            target_year=2027,
            trigger='manual',
            force=True,
        )
        carryover = self._carryover_allocation(2027, 'year_carryover')
        self.assertTrue(carryover)
        self.assertEqual(carryover.number_of_days, 5.0)
        self.assertEqual(logs.carryover_days_capped, expected_capped)

    @freeze_time('2027-01-01 08:00:00')
    def test_manual_wizard_run_for_selected_year(self):
        self._create_allocation('annual_grant', 2026, 21)
        self._create_leave(5, date(2026, 6, 1))
        wizard = self.env['hr.annual.leave.carryover.wizard'].create({
            'company_id': self.company.id,
            'target_year': 2027,
        })
        action = wizard.action_run_carryover()
        self.assertEqual(action['params']['type'], 'success')
        self.assertTrue(self._carryover_allocation(2027, 'year_carryover'))
        self.assertTrue(self._carryover_allocation(2027, 'annual_grant'))

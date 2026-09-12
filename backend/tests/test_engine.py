import unittest

from engine import BreakReport, Liability
from engine.amortization import simulate, total_min_payment
from engine.break_detection import detect_plan_breaks
from engine.feasibility import (
    available_monthly_capacity,
    compute_feasibility,
    project_completion,
)


class AmortizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.liabilities = [
            Liability("a", "BBVA", 10000.0, 0.60, 500.0),
            Liability("b", "Banorte", 5000.0, 0.10, 500.0),
        ]

    def test_simulation_is_deterministic(self) -> None:
        first = simulate(
            monthly_income=3000.0,
            monthly_expenses=1000.0,
            liabilities=self.liabilities,
            strategy="avalanche",
            horizon_months=60,
            extra_payment=500.0,
        )
        second = simulate(
            monthly_income=3000.0,
            monthly_expenses=1000.0,
            liabilities=self.liabilities,
            strategy="avalanche",
            horizon_months=60,
            extra_payment=500.0,
        )
        self.assertEqual(first, second)

    def test_total_min_payment(self) -> None:
        self.assertEqual(total_min_payment(self.liabilities), 1000.0)

    def test_avalanche_costs_no_more_interest_than_snowball(self) -> None:
        common = dict(
            monthly_income=3000.0,
            monthly_expenses=1000.0,
            liabilities=self.liabilities,
            horizon_months=60,
            extra_payment=500.0,
        )
        avalanche = simulate(strategy="avalanche", **common)
        snowball = simulate(strategy="snowball", **common)
        self.assertLessEqual(avalanche.total_interest, snowball.total_interest)
        self.assertIsNotNone(avalanche.payoff_month)
        self.assertIsNotNone(snowball.payoff_month)


class BreakDetectionTest(unittest.TestCase):
    def test_detects_break_at_known_month(self) -> None:
        plan = simulate(
            monthly_income=20000.0,
            monthly_expenses=16500.0,
            liabilities=[Liability("n", "BBVA", 60000.0, 0.54, 3000.0)],
            strategy="minimum",
            horizon_months=12,
            events={7: 10000.0},
        )
        report = detect_plan_breaks(plan)
        self.assertEqual(report, BreakReport(month=7, shortfall=6500.0))

    def test_no_break_for_feasible_plan(self) -> None:
        plan = simulate(
            monthly_income=20000.0,
            monthly_expenses=5000.0,
            liabilities=[Liability("n", "BBVA", 6000.0, 0.30, 3000.0)],
            strategy="avalanche",
            horizon_months=12,
        )
        self.assertIsNone(detect_plan_breaks(plan))


class FeasibilityTest(unittest.TestCase):
    def test_available_monthly_capacity(self) -> None:
        self.assertEqual(available_monthly_capacity(19000.0, 12000.0, 3000.0), 4000.0)

    def test_project_completion_rounds_up(self) -> None:
        self.assertEqual(project_completion(45000.0, 3200.0), 15)

    def test_project_completion_impossible_without_capacity(self) -> None:
        self.assertIsNone(project_completion(45000.0, 0.0))

    def test_compute_feasibility_reports_gap(self) -> None:
        result = compute_feasibility(
            target_amount=45000.0,
            current_saved=0.0,
            monthly_capacity=3200.0,
            months_available=12,
        )
        self.assertEqual(result.months_needed, 15)
        self.assertFalse(result.on_time)
        self.assertEqual(result.gap, 6600.0)


if __name__ == "__main__":
    unittest.main()

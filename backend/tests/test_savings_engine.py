import unittest
from datetime import date

from engine import savings

RESEARCH = {
    "flight_roundtrip_mxn": 28000,
    "lodging_per_night_mxn": 1400,
    "food_per_day_mxn": 700,
    "transport_per_day_mxn": 250,
}
ANSWERS = {"days": "10", "travelers": "2", "origin": "CDMX", "style": "mochilero"}

SEED_CONTEXT = {
    "profile": {"monthlyIncome": 19000.0},
    "incomeStreams": [],
    "cashFlow": {"months": [{"expenses": 15367.09}]},
    "liabilities": [{"minPayment": 7850.0}],
}


class EstimateTest(unittest.TestCase):
    def test_estimate_total_is_deterministic(self) -> None:
        result = savings.estimate_total(RESEARCH, ANSWERS)
        self.assertEqual(result["estimatedTotal"], 77088.0)
        self.assertEqual(result["breakdown"]["flights"], 56000.0)
        self.assertEqual(result["breakdown"]["lodging"], 12600.0)
        self.assertEqual(result["breakdown"]["food"], 14000.0)
        self.assertEqual(result["breakdown"]["transport"], 5000.0)
        self.assertEqual(result["breakdown"]["contingency"], 7008.0)
        self.assertEqual(result["inputs"]["nights"], 9)

    def test_style_multiplier_default(self) -> None:
        self.assertEqual(savings.style_multiplier("desconocido"), 1.0)
        self.assertEqual(savings.style_multiplier("mochilero"), 0.8)
        self.assertEqual(savings.style_multiplier(None), 1.0)

    def test_goal_gap(self) -> None:
        under = savings.goal_gap(90000, 77088.0)
        self.assertEqual(under["status"], "under")
        self.assertEqual(under["gap"], -12912.0)
        over = savings.goal_gap(45000, 77088.0)
        self.assertEqual(over["status"], "over")
        self.assertEqual(over["gap"], 32088.0)

    def test_months_until(self) -> None:
        today = date(2026, 9, 12)
        self.assertEqual(savings.months_until("2027-04-01", today), 7)
        self.assertEqual(savings.months_until("2026-09-01", today), 0)
        self.assertEqual(savings.months_until(None, today), 12)

    def test_financial_capacity_negative_for_seed_persona(self) -> None:
        self.assertEqual(savings.financial_capacity(SEED_CONTEXT), -4217.09)


class BuildPlanTest(unittest.TestCase):
    def test_off_track_when_no_capacity(self) -> None:
        plan = savings.build_savings_plan(
            SEED_CONTEXT,
            {"target_amount": 45000.0, "target_date": "2027-04-01"},
            RESEARCH,
            ANSWERS,
            today=date(2026, 9, 12),
        )
        self.assertEqual(plan["feasibility"], "off_track")
        self.assertIsNone(plan["monthsNeeded"])
        self.assertIsNone(plan["projectedDate"])
        self.assertEqual(plan["fundedTarget"], 0.0)
        self.assertEqual(plan["shortfall"], 77088.0)
        self.assertTrue(plan["redirect"]["recommended"])
        self.assertEqual(plan["redirect"]["reason"], "no_capacity")

    def test_on_track_with_high_capacity(self) -> None:
        context = {
            "profile": {"monthlyIncome": 40000.0},
            "incomeStreams": [],
            "cashFlow": {"months": [{"expenses": 15000.0}]},
            "liabilities": [{"minPayment": 2000.0}],
        }
        plan = savings.build_savings_plan(
            context,
            {"target_amount": 70000.0, "target_date": "2027-04-01"},
            RESEARCH,
            ANSWERS,
            today=date(2026, 9, 12),
        )
        self.assertEqual(plan["monthlyCapacity"], 23000.0)
        self.assertEqual(plan["feasibility"], "on_track")
        self.assertTrue(plan["onTime"])
        self.assertIsNotNone(plan["projectedDate"])
        self.assertFalse(plan["redirect"]["recommended"])

    def test_goal_reduction_reason(self) -> None:
        plan = savings.build_savings_plan(
            SEED_CONTEXT,
            {"target_amount": 45000.0, "target_date": "2027-04-01"},
            RESEARCH,
            ANSWERS,
            today=date(2026, 9, 12),
        )
        redirect = savings.suggest_redirect(plan, goal_reduced=True)
        self.assertEqual(redirect["reason"], "goal_reduction")


if __name__ == "__main__":
    unittest.main()

import unittest

from engine import planning

CONTEXT = {
    "profile": {"monthlyIncome": 20000.0},
    "liabilities": [
        {"id": "a", "creditor": "A", "balance": 10000.0, "apr": 0.6, "minPayment": 1500.0}
    ],
    "incomeStreams": [],
    "cashFlow": {"months": [{"period": "2026-03", "income": 20000.0, "expenses": 16500.0}]},
}


class PlanningTest(unittest.TestCase):
    def test_cashflow_and_liabilities(self) -> None:
        self.assertEqual(planning.monthly_cashflow(CONTEXT), (20000.0, 16500.0))
        liabilities = planning.liabilities_from_context(CONTEXT)
        self.assertEqual(liabilities[0].min_payment, 1500.0)
        self.assertEqual(planning.simulation_inputs(CONTEXT)["minPayment"], 1500.0)

    def test_event_forces_break(self) -> None:
        plan = planning.run_simulation(CONTEXT, events={3: 7000.0})
        self.assertEqual(planning.break_payload(plan), {"month": 3, "shortfall": 1000.0})

    def test_repair_clears_break(self) -> None:
        plan = planning.run_simulation(CONTEXT, events={3: 7000.0}, extra_income=6000.0)
        self.assertIsNone(planning.break_payload(plan))

    def test_build_plan_payload(self) -> None:
        payload = planning.build_plan(CONTEXT, {"events": {"3": 7000.0}})
        self.assertEqual(payload["breakMonth"], 3)
        self.assertEqual(payload["break"]["shortfall"], 1000.0)
        self.assertTrue(payload["months"])
        self.assertIn("payoffMonth", payload)


if __name__ == "__main__":
    unittest.main()

import unittest

from engine import offer

CONTEXT = {
    "profile": {"monthlyIncome": 19000.0},
    "liabilities": [
        {"id": "a", "creditor": "BBVA", "balance": 48000.0, "apr": 0.54, "minPayment": 2900.0},
        {"id": "b", "creditor": "BBVA", "balance": 35000.0, "apr": 0.28, "minPayment": 1800.0},
    ],
    "cashFlow": {"months": [{"period": "2026-03", "income": 19000.0, "expenses": 15367.09}]},
}

POLICIES = [
    {"id": "p1", "creditor": "BBVA", "strategy": "consolidation", "minSettlementPct": 1.0, "maxMonths": 48, "aprFloor": 0.24, "acceptsConsolidation": True},
    {"id": "p2", "creditor": "BBVA", "strategy": "settlement", "minSettlementPct": 0.70, "maxMonths": 12, "aprFloor": 0.0, "acceptsConsolidation": False},
]


class OfferEngineTest(unittest.TestCase):
    def test_consolidation_offer_within_bounds(self) -> None:
        result = offer.generate_offer(CONTEXT, POLICIES, strategy="consolidation")
        self.assertEqual(result["status"], "ok")
        terms = result["offer"]
        self.assertEqual(terms["principal"], 83000.0)
        self.assertEqual(terms["months"], 48)
        self.assertGreaterEqual(terms["apr"], 0.24)
        self.assertGreater(terms["monthlyPayment"], 0)

    def test_settlement_offer(self) -> None:
        terms = offer.generate_offer(CONTEXT, POLICIES, strategy="settlement")["offer"]
        self.assertEqual(terms["principal"], 58100.0)
        self.assertEqual(terms["apr"], 0.0)
        self.assertEqual(terms["months"], 12)
        self.assertAlmostEqual(terms["monthlyPayment"], 4841.67, places=2)

    def test_evaluate_feasible_and_infeasible(self) -> None:
        feasible = offer.evaluate_offer(
            CONTEXT,
            {"principal": 83000.0, "apr": 0.05, "months": 60, "monthlyPayment": 3500.0},
        )
        self.assertTrue(feasible["feasible"])
        self.assertIsNone(feasible["break"])

        infeasible = offer.evaluate_offer(
            CONTEXT,
            {"principal": 83000.0, "apr": 0.05, "months": 60, "monthlyPayment": 5000.0},
        )
        self.assertFalse(infeasible["feasible"])
        self.assertEqual(infeasible["break"]["month"], 1)

    def test_choose_policy_by_creditor(self) -> None:
        self.assertEqual(offer.choose_policy(POLICIES, creditor="BBVA", strategy="settlement")["id"], "p2")


if __name__ == "__main__":
    unittest.main()

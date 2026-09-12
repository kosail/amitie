"""Deterministic loan offer + risk framework."""

import unittest

from engine import loan_offer

CONTEXT = {
    "profile": {"monthlyIncome": 30000.0, "payFrequency": "quincenal"},
    "liabilities": [
        {"id": "l1", "creditor": "BBVA", "balance": 50000.0, "apr": 0.5, "minPayment": 2000.0}
    ],
    "subscriptions": [{"amount": 300.0, "period": "mensual"}],
    "cashFlow": {
        "months": [
            {"income": 30000.0, "expenses": 12000.0, "net": 18000.0},
            {"income": 30000.0, "expenses": 13000.0, "net": 17000.0},
        ]
    },
    "subscriptionTotal": 300.0,
}

POLICIES = [{"creditor": "BBVA", "strategy": "consolidation", "aprFloor": 0.24}]
GOALS = [{"name": "Viaje a Japón", "targetAmount": 45000.0, "currentSaved": 0.0}]
HISTORY = [{"status": "on_time"}] * 5 + [{"status": "late"}]


class LoanOfferTest(unittest.TestCase):
    def test_offer_is_deterministic_and_affordable(self) -> None:
        first = loan_offer.propose_offer(CONTEXT, lender_policies=POLICIES)
        second = loan_offer.propose_offer(CONTEXT, lender_policies=POLICIES)
        self.assertEqual(first, second)

        offer = first["offer"]
        self.assertGreater(offer["amount"], 0)
        self.assertEqual(len(first["schedule"]), offer["termMonths"])
        # DTI stays within the cap.
        self.assertLessEqual(first["risk"]["dti"]["withOffer"], first["risk"]["dti"]["cap"] + 1e-9)
        self.assertTrue(first["affordable"])
        # CAT includes fees, so it exceeds the APR.
        self.assertGreater(offer["cat"], offer["apr"])
        self.assertGreater(first["risk"]["surplus"]["monthly"], 0)

    def test_requested_amount_caps_and_rounds(self) -> None:
        small = loan_offer.propose_offer(CONTEXT, requested_amount=8000.0)
        self.assertEqual(small["offer"]["amount"], 8000.0)
        huge = loan_offer.propose_offer(CONTEXT, requested_amount=10_000_000.0)
        self.assertLess(huge["offer"]["amount"], 10_000_000.0)

    def test_relative_cost_and_history_and_savings(self) -> None:
        result = loan_offer.propose_offer(
            CONTEXT,
            lender_policies=POLICIES,
            saving_goals=GOALS,
            payment_history=HISTORY,
        )
        # Offered APR (24%) beats the existing 50% credit -> not worse.
        self.assertFalse(result["risk"]["relativeCost"]["worse"])
        self.assertTrue(result["risk"]["paymentHistory"]["available"])
        self.assertLess(result["risk"]["paymentHistory"]["projectedScoreDelta"], 8)
        self.assertIsNotNone(result["risk"]["savingsImpact"])

    def test_compute_cat_zero_for_zero_amount(self) -> None:
        self.assertEqual(loan_offer.compute_cat(0, 0.24, 24, 0, 0), 0.0)


if __name__ == "__main__":
    unittest.main()
